"""Tests for gentoo build publisher"""
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from gentoo_build_publisher.conf import settings

BASE_DIR = Path(__file__).resolve().parent / "data"


def test_data(filename):
    """Return all the data in filename"""
    with open(BASE_DIR / filename, "rb") as file_obj:
        return file_obj.read()


@contextmanager
def mock_get_artifact():
    """Mock the downloading of the artifact from Jenkins"""
    with mock.patch("gentoo_build_publisher.models.requests.get") as mock_get:
        response = mock_get.return_value
        response.iter_content.return_value = iter([test_data("build.tar.gz")])

        yield mock_get


@contextmanager
def mock_home_dir():
    """Mock the home directory setting into a new TemporaryDirectory"""
    with tempfile.TemporaryDirectory() as home_dir:
        with mock.patch.object(settings, "HOME_DIR", home_dir):

            yield home_dir
