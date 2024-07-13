"""Misc utilities"""

from __future__ import annotations

import base64
import importlib.resources
import platform
import re
import string
from functools import partial, wraps
from importlib.metadata import version
from typing import Any, Callable, Collection, NamedTuple, ParamSpec, Self, TypeVar

import requests
from cryptography.fernet import Fernet
from yarl import URL

CPV = re.compile(r"(?P<cat>.*)/(?P<pkg>.*)-(?P<version>[0-9].*)")
INVALID_IDENTIFIER_START = {".", "-"}
VALID_IDENTIFIER_CHARS = set([*string.ascii_letters, *string.digits, "_", ".", "-"])
MAXIMUM_IDENTIFIER_LENGTH = 128


class Color(NamedTuple):
    """Data structure representing an rgb color"""

    red: int
    green: int
    blue: int

    def __str__(self) -> str:
        return f"#{self.red:02x}{self.green:02x}{self.blue:02x}"

    @classmethod
    def gradient(
        cls: type[Self], start: Self, end: Self, num_colors: int
    ) -> list[Self]:
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


class InvalidIdentifier(ValueError):
    """The given identifier name is invalid"""


def get_hostname() -> str:
    """Return the system's hostname"""
    return platform.node()


def get_version() -> str:
    """Return package version"""
    return version("gentoo_build_publisher")


def cpv_to_path(cpv: str, build_id: int = 1, extension: str = ".gpkg.tar") -> str:
    """Return the relative path of the would-be package"""
    if not (cpv_match := CPV.match(cpv)):
        raise ValueError(cpv)

    cat, pkg, ver = cpv_match.groups()

    return f"{cat}/{pkg}/{pkg}-{ver}-{build_id}{extension}"


def validate_identifier(name: str) -> None:
    """Check if the given string is a valid identifier

    Raise InvalidIdentifier if not a valid name

    Tag names have the following requirements:

        * ASCII characters
        * contain lowercase and uppercase letters, digits, underscores, periods and
          dashes
        * must not start with a period, or dash
        * Must be a maximum of 128 characters
    """
    # This is based off of Docker's image tagging rules
    # https://docs.docker.com/engine/reference/commandline/tag/
    error = InvalidIdentifier(repr(name))
    if not name:
        raise error

    if len(name) > MAXIMUM_IDENTIFIER_LENGTH:
        raise error

    if name[0] in INVALID_IDENTIFIER_START:
        raise error

    if not set(name[1:]) <= VALID_IDENTIFIER_CHARS:
        raise error


def encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt `data` given the symmetric `key`"""
    cipher_suite = Fernet(key)
    encrypted = cipher_suite.encrypt(data)

    return encrypted


def decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt `data` given the symmetric `key`"""
    cipher_suite = Fernet(key)
    decrypted = cipher_suite.decrypt(data)

    return decrypted


def create_secret_key() -> bytes:
    """Return a byte string useful as a secret key"""
    return Fernet.generate_key()


def read_package_file(filename: str) -> str:
    """Read the given filename from this package"""
    return importlib.resources.read_text(
        "gentoo_build_publisher", filename, encoding="UTF-8"
    )


def ensure_bytes(data: str | bytes, encoding: str = "ascii") -> bytes:
    """Return data as bytes"""
    if isinstance(data, bytes):
        return bytes(data)
    if isinstance(data, str):
        return data.encode(encoding)
    raise ValueError("Argument must be an instance of str or bytes")


def ensure_str(data: str | bytes, encoding: str = "ascii") -> str:
    """Return data as str"""
    if isinstance(data, str):
        return str(data)
    if isinstance(data, bytes):
        return data.decode(encoding)
    raise ValueError("Argument must be an instance of str or bytes")


def dict_to_list_of_dicts(
    data: dict[str, Any], key_key: str = "name", value_key: str = "value"
) -> list[dict[str, Any]]:
    """Convert a dict to a list of dicts

    >>> d = {"first": "albert", "last": "hopkins"}
    >>> dict_to_list_of_dicts(d)
    [{"name": "first", "value": "albert"}, {"name": "last", "value": "hopkins"}]
    """
    return [{key_key: key, value_key: value} for key, value in data.items()]


P = ParamSpec("P")
F = TypeVar("F", bound=Callable[P, Any])


def conditionally(
    condition: bool | Callable[[], bool], decorator: Callable[[F], F]
) -> Callable[[F], F | Callable[P, Any]]:
    """Decorator to conditionally apply another decorator

    If condition is a callable, it will be called without arguments and the value
    returned sets the condition.
    """

    def dec(func: F) -> F | Callable[P, Any]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            mycondition: bool = condition() if callable(condition) else condition

            return (
                decorator(func)(*args, **kwargs)
                if mycondition
                else func(*args, **kwargs)
            )

        return wrapper

    return dec


def request_and_raise(
    request: Callable[..., requests.Response],
    url: str | URL,
    *args: Any,
    exclude: Collection[int] | None = None,
    **kwargs: Any,
) -> requests.Response:
    """Wrapper for resp = requests.request() ... resp.raise_for_status()

    Except it will not call raise_for_status() for responses with status codes in the
    exclude list.
    """
    response = request(str(url), *args, **kwargs)

    if not (exclude and response.status_code in exclude):
        response.raise_for_status()

    return response


def parse_basic_auth_header(header_value: str) -> tuple[str, str]:
    """Parse a Basic Auth header value and return the user and secret"""
    if header_value.startswith("Basic "):
        value_encoded = header_value[6:].strip()
        value = ensure_str(base64.b64decode(ensure_bytes(value_encoded)))
        user, colon, secret = value.partition(":")
        if colon:
            return user, secret

    raise ValueError("Invalid Bearer Authentication value")


def encode_basic_auth_data(username: str, secret: str) -> str:
    """Encode username and secret for use in a Basic Auth header value

    Does not include the "Basic " string.
    """
    value = f"{username}:{secret}".encode("ascii")

    return base64.b64encode(value).decode("ascii")


encode = partial(str.encode, encoding="ascii")
decode = partial(bytes.decode, encoding="ascii")
