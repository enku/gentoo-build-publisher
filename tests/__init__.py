"""Tests for gentoo build publisher"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent / "data"


def test_data(filename):
    """Return all the data in filename"""
    with open(BASE_DIR / filename, "rb") as file_obj:
        return file_obj.read()
