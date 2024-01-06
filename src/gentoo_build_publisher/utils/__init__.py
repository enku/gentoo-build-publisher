"""Misc utilities"""
from __future__ import annotations

import datetime as dt
import importlib.resources
import platform
import re
import string
from importlib.metadata import version
from typing import Any, NamedTuple, TypeVar

IT = TypeVar("IT")
T = TypeVar("T", bound="Color")  # pylint: disable=invalid-name

CPV = re.compile(r"(?P<cat>.*)/(?P<pkg>.*)-(?P<version>[0-9].*)")
INVALID_TAG_START = {".", "-"}
VALID_TAG_CHARS = set([*string.ascii_letters, *string.digits, "_", ".", "-"])
MAXIMUM_TAG_LENGTH = 128


class Color(NamedTuple):
    """Data structure representing an rgb color"""

    red: int
    green: int
    blue: int

    def __str__(self) -> str:
        return f"#{self.red:02x}{self.green:02x}{self.blue:02x}"

    @classmethod
    def gradient(cls: type[T], start: T, end: T, num_colors: int) -> list[T]:
        """Return a list of colors representing a gradient from `start` to `end`"""
        if num_colors < 1:
            return []

        if num_colors == 1:
            return [start]

        if num_colors == 2:
            return [start, end]

        colors = [start]

        steps = num_colors - 1
        inc_red = (end.red - start.red) / steps
        inc_green = (end.green - start.green) / steps
        inc_blue = (end.blue - start.blue) / steps

        new_red = float(start.red)
        new_green = float(start.green)
        new_blue = float(start.blue)

        for _ in range(num_colors - 2):
            new_red = new_red + inc_red
            new_green = new_green + inc_green
            new_blue = new_blue + inc_blue
            colors.append(cls(int(new_red), int(new_green), int(new_blue)))

        colors.append(end)

        return colors


class InvalidTagName(ValueError):
    """The given tag name is invalid"""


def get_hostname() -> str:
    """Return the system's hostname"""
    return platform.node()


def get_version() -> str:
    """Return package version"""
    return version("gentoo_build_publisher")


def lapsed(start: dt.datetime, end: dt.datetime) -> int:
    """Return the number of seconds between `start` and `end`"""
    return int((end - start).total_seconds())


def cpv_to_path(cpv: str, build_id: int = 1, extension: str = ".xpak") -> str:
    """Return the relative path of the would-be package"""
    if not (cpv_match := CPV.match(cpv)):
        raise ValueError(cpv)

    cat, pkg, ver = cpv_match.groups()

    return f"{cat}/{pkg}/{pkg}-{ver}-{build_id}{extension}"


def check_tag_name(tag_name: str) -> None:
    """Check if the given string is a valid tag name

    Raise InvalidTagName if not a valid tag name

    Tag names have the following requirements:

        * ASCII characters
        * contain lowercase and uppercase letters, digits, underscores, periods and
          dashes
        * must not start with a period, or dash
        * Must be a maximum of 128 characters
        * In addition the empty string is a valid tag
    """
    # This is based off of Docker's image tagging rules
    # https://docs.docker.com/engine/reference/commandline/tag/
    if not tag_name:
        return

    if len(tag_name) > MAXIMUM_TAG_LENGTH:
        raise InvalidTagName(tag_name)

    if tag_name[0] in INVALID_TAG_START:
        raise InvalidTagName(tag_name)

    if not set(tag_name[1:]) <= VALID_TAG_CHARS:
        raise InvalidTagName(tag_name)


def utctime(time: dt.datetime | None = None) -> dt.datetime:
    """Return time but with the timezone being UTC"""
    if time is None:
        time = dt.datetime.utcnow()

    return time.replace(tzinfo=dt.timezone.utc)


def read_package_file(filename: str) -> str:
    """Read the given filename from this package"""
    return importlib.resources.read_text(
        "gentoo_build_publisher", filename, encoding="UTF-8"
    )


def dict_to_list_of_dicts(
    data: dict[str, Any], key_key: str = "name", value_key: str = "value"
) -> list[dict[str, Any]]:
    """Convert a dict to a list of dicts

    >>> d = {"first": "albert", "last": "hopkins"}
    >>> dict_to_list_of_dicts(d)
    [{"name": "first", "value": "albert"}, {"name": "last", "value": "hopkins"}]
    """
    return [{key_key: key, value_key: value} for key, value in data.items()]
