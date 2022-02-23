"""Tests for gentoo build publisher"""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name
import logging
import os
import tempfile
from pathlib import Path
from typing import Union
from unittest import mock

import django.test

from gentoo_build_publisher.jenkins import Jenkins, JenkinsMetadata
from gentoo_build_publisher.publisher import BuildPublisher, build_publisher
from gentoo_build_publisher.types import Build

BASE_DIR = Path(__file__).resolve().parent / "data"

# This is the list of packages (in order) stored in the artifact fixture
PACKAGE_INDEX: list[str] = [
    "acct-group/sgx-0",
    "app-admin/perl-cleaner-2.30",
    "app-arch/unzip-6.0_p26",
    "app-crypt/gpgme-1.14.0",
]


logging.basicConfig(handlers=[logging.NullHandler()])


class TestCase(django.test.TestCase):
    def setUp(self):
        super().setUp()

        build_publisher.reset()
        tmpdir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(tmpdir.cleanup)
        self.tmpdir = Path(tmpdir.name)
        patch = mock.patch.dict(
            os.environ,
            {
                "BUILD_PUBLISHER_STORAGE_PATH": tmpdir.name,
                "BUILD_PUBLISHER_JENKINS_BASE_URL": "https://jenkins.invalid/",
            },
        )
        self.addCleanup(patch.stop)
        patch.start()

    def create_file(self, name, content=b"", mtime=None):
        path = self.tmpdir / name

        with path.open("wb") as outfile:
            outfile.write(content)

        if mtime is not None:
            stat = os.stat(path)
            atime = stat.st_atime
            os.utime(path, times=(atime, mtime.timestamp()))

        return path


def test_data(filename):
    """Return all the data in filename"""
    with open(BASE_DIR / filename, "rb") as file_obj:
        return file_obj.read()


class MockJenkins(Jenkins):
    """Jenkins with requests mocked out"""

    mock_get = None
    get_build_logs_mock_get = None

    def download_artifact(self, build: Build):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.iter_content.side_effect = (
                lambda *args, **kwargs: iter([test_data("build.tar.gz")])
            )
            self.mock_get = mock_get
            return super().download_artifact(build)

    def get_logs(self, build: Build):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.text = "foo\n"
            self.get_build_logs_mock_get = mock_get

            return super().get_logs(build)

    def get_metadata(self, build: Build) -> JenkinsMetadata:
        return JenkinsMetadata(duration=124, timestamp=1620525666000)


def package_entry(
    cpv: Union[str, list[str]], build_id: int = 1, repo: str = "gentoo", size: int = 0
) -> str:
    if isinstance(cpv, str):
        cpvs = [cpv]
    else:
        cpvs = cpv

    strings = []

    for _cpv in cpvs:
        cat, rest = _cpv.rsplit("/", 1)
        pkg, version = rest.split("-", 1)

        strings.append(
            "\n"
            f"BUILD_ID: {build_id}\n"
            f"CPV: {_cpv}\n"
            f"SIZE: {size}\n"
            f"REPO: {repo}\n"
            f"PATH: {cat}/{pkg}/{pkg}-{version}-{build_id}.xpak\n"
            f"BUILD_TIME: 1622722899\n"
        )

    return "".join(["Ignore Preamble\n", *strings])
