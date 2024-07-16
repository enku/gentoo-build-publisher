# pylint: disable=missing-docstring,too-few-public-methods
from types import SimpleNamespace
from typing import Any, Callable, Iterator, TypeAlias


class Fixtures(SimpleNamespace):
    pass


class FixtureRequired(ValueError):
    pass


SetupOptions: TypeAlias = dict[str, Any]
SetupContext: TypeAlias = Iterator
SetupFunction: TypeAlias = Callable[[SetupOptions, Fixtures], Any]
SetupSpec: TypeAlias = str | SetupFunction
