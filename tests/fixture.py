"""Fixtures framework"""

# pylint: disable=missing-docstring,protected-access
import copy
import inspect
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace
from typing import Any, Callable, Iterable, Iterator, TypeAlias
from unittest import TestCase

_REQUIREMENTS = {}

Fixtures: TypeAlias = SimpleNamespace
FixtureOptions: TypeAlias = dict[str, Any]
FixtureContext: TypeAlias = Iterator
FixtureFunction: TypeAlias = Callable[[FixtureOptions, Fixtures], Any]
FixtureSpec: TypeAlias = str | FixtureFunction


class BaseTestCase(TestCase):
    _options: FixtureOptions
    options: FixtureOptions = {}
    fixtures: Fixtures


def load(spec: FixtureSpec) -> FixtureFunction:
    try:
        # pylint: disable=import-outside-toplevel
        from . import fixtures as fixtures_module
    except ImportError:
        fixtures_module = ModuleType("fixtures")
    func: FixtureFunction = (
        getattr(fixtures_module, spec) if isinstance(spec, str) else spec
    )

    return func


def depends(*deps: FixtureSpec) -> Callable[[FixtureFunction], FixtureFunction]:
    def dec(fn: FixtureFunction) -> FixtureFunction:
        fn._deps = list(deps)  # type: ignore[attr-defined]
        return fn

    return dec


def requires(
    *requirements: FixtureSpec,
) -> Callable[[type[BaseTestCase]], type[BaseTestCase]]:
    def decorator(test_case: type[BaseTestCase]) -> type[BaseTestCase]:
        setups = {}
        for requirement in requirements:
            func = load(requirement)
            name = func.__name__.removesuffix("_fixture")
            setups[name] = func
        _REQUIREMENTS[test_case] = setups

        def setup(self: BaseTestCase) -> None:
            super(test_case, self).setUp()

            self.fixtures = getattr(self, "fixtures", None) or Fixtures()
            self._options = getattr(self, "_options", {})
            self._options.update(getattr(test_case, "options", {}))

            setups = _REQUIREMENTS.get(test_case, {})
            add_funcs(self, setups.values())

        setattr(test_case, "setUp", setup)
        return test_case

    return decorator


def add_funcs(test: BaseTestCase, specs: Iterable[FixtureSpec]) -> None:
    for func in [load(spec) for spec in specs]:
        name = func.__name__.removesuffix("_fixture")
        if deps := getattr(func, "_deps", []):
            add_funcs(test, deps)
        if not hasattr(test.fixtures, name):
            setattr(test.fixtures, name, get_result(func, test))


def get_result(func: FixtureFunction, test: BaseTestCase) -> Any:
    if inspect.isgeneratorfunction(func):
        return test.enterContext(
            contextmanager(func)(test._options, copy.copy(test.fixtures))
        )

    return func(test._options, copy.copy(test.fixtures))
