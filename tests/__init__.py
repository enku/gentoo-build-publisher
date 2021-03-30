"""Tests for gentoo build publisher"""
import os
import tempfile
from pathlib import Path
from unittest import mock

from gentoo_build_publisher.conf import GBPSettings
from gentoo_build_publisher.types import Jenkins

BASE_DIR = Path(__file__).resolve().parent / "data"


def mock_settings(**kwargs):
    with mock.patch.dict(os.environ, {}, clear=True):
        settings = GBPSettings(
            "",
            {
                "HOME_DIR": "/var/lib/gentoo-build-publisher",
                "JENKINS_API_KEY": "test_key",
                "JENKINS_ARTIFACT_NAME": "test.tar.gz",
                "JENKINS_BASE_URL": "https://test.invalid",
                "JENKINS_USER": "test_user",
            },
        )
        for name, value in kwargs.items():
            setattr(settings, name, value)

        return settings


class TempDirMixin:
    def setUp(self):
        super().setUp()

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.tmpdir = tmpdir.name


def test_data(filename):
    """Return all the data in filename"""
    with open(BASE_DIR / filename, "rb") as file_obj:
        return file_obj.read()


class MockJenkins(Jenkins):
    """Jenkins with requests mocked out"""

    mock_get = None

    def download_artifact(self, build):
        with mock.patch("gentoo_build_publisher.types.requests.get") as mock_get:
            mock_get.return_value.iter_content.side_effect = (
                lambda *args, **kwargs: iter([test_data("build.tar.gz")])
            )
            self.mock_get = mock_get
            return super().download_artifact(build)


def mock_home_dir(func=None):
    """Mock the settings.HOME_DIR setting into a new TemporaryDirectory"""
    with tempfile.TemporaryDirectory() as home_dir:
        patch = mock.patch("gentoo_build_publisher.conf.settings.HOME_DIR", home_dir)

        return patch if func is None else patch(func)
