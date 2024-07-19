# pylint: disable=missing-docstring,too-few-public-methods
from types import SimpleNamespace
from typing import Any, Callable, Iterator, TypeAlias
from unittest import TestCase


class Fixtures(SimpleNamespace):
    pass


SetupOptions: TypeAlias = dict[str, Any]
SetupContext: TypeAlias = Iterator
SetupFunction: TypeAlias = Callable[[SetupOptions, Fixtures], Any]
SetupSpec: TypeAlias = str | SetupFunction


class BaseTestCase(TestCase):
    _options: SetupOptions
    options: SetupOptions = {}
    fixtures: Fixtures
