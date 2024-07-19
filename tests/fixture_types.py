# pylint: disable=missing-docstring,too-few-public-methods
from types import SimpleNamespace
from typing import Any, Callable, Iterator, TypeAlias
from unittest import TestCase


class Fixtures(SimpleNamespace):
    pass


FixtureOptions: TypeAlias = dict[str, Any]
FixtureContext: TypeAlias = Iterator
FixtureFunction: TypeAlias = Callable[[FixtureOptions, Fixtures], Any]
FixtureSpec: TypeAlias = str | FixtureFunction


class BaseTestCase(TestCase):
    _options: FixtureOptions
    options: FixtureOptions = {}
    fixtures: Fixtures
