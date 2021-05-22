"""Tests for gentoo build publisher"""
import os
import tempfile
from pathlib import Path
from unittest import mock

from gentoo_build_publisher import Jenkins

BASE_DIR = Path(__file__).resolve().parent / "data"


class TempHomeMixin:
    def setUp(self):
        super().setUp()

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.tmpdir = Path(tmpdir.name)
        patch = mock.patch.dict(
            os.environ,
            {
                "BUILD_PUBLISHER_HOME_DIR": tmpdir.name,
                "BUILD_PUBLISHER_JENKINS_BASE_URL": "/dev/null",
            },
        )
        self.addCleanup(patch.stop)
        patch.start()


def test_data(filename):
    """Return all the data in filename"""
    with open(BASE_DIR / filename, "rb") as file_obj:
        return file_obj.read()


class MockJenkins(Jenkins):
    """Jenkins with requests mocked out"""

    mock_get = None

    def download_artifact(self, build):
        with mock.patch("gentoo_build_publisher.requests.get") as mock_get:
            mock_get.return_value.iter_content.side_effect = (
                lambda *args, **kwargs: iter([test_data("build.tar.gz")])
            )
            self.mock_get = mock_get
            return super().download_artifact(build)
