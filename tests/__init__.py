"""Tests for gentoo build publisher"""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name
import io
import json
import logging
import math
import os
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Union
from unittest import mock

import django.test

from gentoo_build_publisher.jenkins import Jenkins, JenkinsConfig, JenkinsMetadata
from gentoo_build_publisher.publisher import BuildPublisher, build_publisher
from gentoo_build_publisher.types import Build, Content, Package
from gentoo_build_publisher.utils import cpv_to_path

BASE_DIR = Path(__file__).resolve().parent / "data"

# This is the default list of packages (in order) stored in the artifacts
PACKAGE_INDEX: list[str] = [
    "acct-group/sgx-0",
    "app-admin/perl-cleaner-2.30",
    "app-arch/unzip-6.0_p26",
    "app-crypt/gpgme-1.14.0",
]


logging.basicConfig(handlers=[logging.NullHandler()])


class TestCase(django.test.TestCase):
    def setUp(self):
        # pylint: disable=import-outside-toplevel,cyclic-import
        from .factories import BuildPublisherFactory

        super().setUp()

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

        test_publisher = BuildPublisherFactory()
        build_publisher.reset(test_publisher)
        self.artifact_builder = test_publisher.jenkins.artifact_builder

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

    def __init__(self, config: JenkinsConfig):

        super().__init__(config)

        self.artifact_builder = ArtifactBuilder()

    def download_artifact(self, build: Build):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.iter_content.side_effect = (
                lambda *args, **kwargs: self.artifact_builder.get_artifact()
            )
            self.mock_get = mock_get
            return super().download_artifact(build)

    def get_logs(self, build: Build):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.text = "foo\n"
            self.get_build_logs_mock_get = mock_get

            return super().get_logs(build)

    def get_metadata(self, build: Build) -> JenkinsMetadata:
        return JenkinsMetadata(duration=124, timestamp=self.artifact_builder.timestamp)


class ArtifactBuilder:
    """Build CI/CD artifacts dynamically"""

    initial_packages = [
        "acct-group/sgx-0",
        "app-admin/perl-cleaner-2.30",
        "app-arch/unzip-6.0_p26",
        "app-crypt/gpgme-1.14.0",
    ]

    def __init__(self, initial_packages=None, timestamp=None):
        self.packages = []

        if timestamp is None:
            self.timestamp = int(time.time() * 1000)
        else:
            self.timestamp = timestamp

        self.timer = int(self.timestamp / 1000)
        yesterday = self.timer - 86400

        if initial_packages is None:
            initial_packages = self.initial_packages

        for cpv in initial_packages:
            self.build(cpv, build_time=yesterday)

    def build(
        self, cpv: str, repo="gentoo", build_id: int = 1, build_time: int | None = None
    ) -> Package:
        """Pretend we've built a package and add it to the package index"""
        if build_time is None:
            timestamp = self.advance()
            build_time = timestamp

        path = cpv_to_path(cpv, build_id)
        size = len(cpv) ** 2
        package = Package(cpv, repo, path, build_id, size, build_time)
        self.packages.append(package)

        return package

    def remove(self, package: Package):
        """Remove a package from the build"""
        self.packages.remove(package)

    def get_artifact(self) -> io.BytesIO:
        """Return a file-like object representing a CI/CD artifact"""
        tar_file = io.BytesIO()

        with tarfile.open("build.tar.gz", "x:gz", tar_file) as tarchive:

            timestamp = self.advance()
            self.add_to_tarchive(
                tarchive,
                "binpkgs/Packages",
                self.index().encode("utf-8"),
                mtime=timestamp,
            )

            gbp_json = {
                "machine": "babette",
                "build": "1",
                "date": int(math.floor(self.timestamp / 1000)),
                "buildHost": "lighthouse",
            }
            self.add_to_tarchive(
                tarchive,
                "binpkgs/gbp.json",
                json.dumps(gbp_json).encode("utf-8"),
                mtime=timestamp,
            )

            for package in self.packages:
                self.add_to_tarchive(
                    tarchive, f"binpkgs/{package.path}", b"", mtime=package.build_time
                )

            for item in Content:
                tar_info = tarfile.TarInfo(item.value)
                tar_info.type = tarfile.DIRTYPE
                tar_info.mode = 0o0755
                tarchive.addfile(tar_info)

        tar_file.seek(0)

        return tar_file

    def index(self) -> str:
        """Return the package index a-la Packages"""
        strings = [
            (
                "\n"
                f"BUILD_ID: {package.build_id}\n"
                f"CPV: {package.cpv}\n"
                f"SIZE: {package.size}\n"
                f"REPO: {package.repo}\n"
                f"PATH: {cpv_to_path(package.cpv, package.build_id)}\n"
                f"BUILD_TIME: {package.build_time}\n"
            )
            for package in self.packages
        ]

        return "".join(["Ignore Preamble\n", *strings])

    @staticmethod
    def add_to_tarchive(
        tarchive: tarfile.TarFile,
        arcname: str,
        content: bytes,
        mtime: int | None = None,
    ):
        file_obj = io.BytesIO(content)
        tar_info = tarfile.TarInfo(arcname)
        tar_info.size = len(content)
        tar_info.mode = 0o0644

        if mtime is None:
            tar_info.mtime = int(time.time())
        else:
            tar_info.mtime = mtime

        tarchive.addfile(tar_info, file_obj)

    def advance(self, seconds: int = 10) -> int:
        self.timer += seconds

        return self.timer
