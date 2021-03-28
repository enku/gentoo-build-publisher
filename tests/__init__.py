"""Tests for gentoo build publisher"""
import tempfile
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent / "data"


def test_data(filename):
    """Return all the data in filename"""
    with open(BASE_DIR / filename, "rb") as file_obj:
        return file_obj.read()


def mock_get_artifact(func=None):
    """Mock the downloading of the artifact from Jenkins"""
    mock_get = mock.Mock()
    mock_get.return_value.iter_content.side_effect = lambda *args, **kwargs: iter(
        [test_data("build.tar.gz")]
    )
    patch = mock.patch("gentoo_build_publisher.models.requests.get", mock_get)

    return patch if func is None else patch(func)


def mock_home_dir(func=None):
    """Mock the settings.HOME_DIR setting into a new TemporaryDirectory"""
    with tempfile.TemporaryDirectory() as home_dir:
        patch = mock.patch("gentoo_build_publisher.conf.settings.HOME_DIR", home_dir)

        return patch if func is None else patch(func)
