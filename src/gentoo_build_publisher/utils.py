"""Misc utilties"""
import datetime as dt
import socket
from dataclasses import dataclass
from importlib.metadata import version
from typing import Type, TypeVar

T = TypeVar("T", bound="Color")  # pylint: disable=invalid-name


@dataclass
class Color:
    """Data structure representing an rgb color"""

    red: int
    green: int
    blue: int

    def __str__(self) -> str:
        return f"#{self.red:02x}{self.green:02x}{self.blue:02x}"

    @classmethod
    def gradient(cls: Type[T], start: T, end: T, num_colors: int) -> list[T]:
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


def get_hostname() -> str:
    """Return the system's hostname"""
    return socket.gethostname()


def get_version() -> str:
    """Return package version"""
    return version("gentoo_build_publisher")


def lapsed(start: dt.datetime, end: dt.datetime) -> int:
    """Return the number of seconds between `start` and `end`"""
    return int((end - start).total_seconds())
