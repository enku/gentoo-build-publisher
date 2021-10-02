"""Tests for gentoo build publisher"""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name
import logging
import os
import tempfile
from pathlib import Path
from unittest import mock

import django.test

from gentoo_build_publisher.jenkins import JenkinsBuild

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


def test_data(filename):
    """Return all the data in filename"""
    with open(BASE_DIR / filename, "rb") as file_obj:
        return file_obj.read()


class MockJenkinsBuild(JenkinsBuild):
    """JenkinsBuild with requests mocked out"""

    mock_get = None
    get_build_logs_mock_get = None

    def download_artifact(self):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.iter_content.side_effect = (
                lambda *args, **kwargs: iter([test_data("build.tar.gz")])
            )
            self.mock_get = mock_get
            return super().download_artifact()

    def get_logs(self):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.text = "foo\n"
            self.get_build_logs_mock_get = mock_get

            return super().get_logs()
