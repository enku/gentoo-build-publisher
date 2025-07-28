"""helpers for writing tests"""

# pylint: disable=missing-docstring
from typing import Any
from unittest import mock


def make_entry_point(name: str, loaded_value: Any) -> mock.Mock:
    ep = mock.Mock()
    ep.name = name
    ep.load.return_value = loaded_value
    return ep
