"""Fixtures"""

# pylint: disable=missing-docstring,protected-access
import copy
import datetime as dt
import importlib.metadata
import itertools
import os
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any, Callable, Iterable
from unittest import mock

from cryptography.fernet import Fernet
from django.test.client import Client
from gbpcli import GBP

from gentoo_build_publisher import publisher as publisher_mod
from gentoo_build_publisher.cli import apikey
from gentoo_build_publisher.jenkins import Jenkins
from gentoo_build_publisher.models import BuildLog, BuildModel
from gentoo_build_publisher.records import BuildRecord, RecordDB
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage
from gentoo_build_publisher.types import ApiKey, Build
from gentoo_build_publisher.utils import time

from .factories import BuildFactory, BuildModelFactory, BuildPublisherFactory
from .fixture_types import (
    BaseTestCase,
    FixtureContext,
    FixtureFunction,
    FixtureOptions,
    Fixtures,
    FixtureSpec,
)
from .helpers import MockJenkins, create_user_auth, string_console, test_gbp

_REQUIREMENTS = {}
BuildPublisher = publisher_mod.BuildPublisher
now = partial(dt.datetime.now, tz=dt.UTC)


def load(spec: FixtureSpec) -> FixtureFunction:
    func: FixtureFunction = globals()[spec] if isinstance(spec, str) else spec

    return func


def depends(*deps: FixtureSpec) -> Callable[[FixtureFunction], FixtureFunction]:
    def dec(fn: FixtureFunction) -> FixtureFunction:
        fn._deps = [load(dep) for dep in deps]  # type: ignore[attr-defined]
        return fn

    return dec


@contextmanager
def tmpdir(_options: FixtureOptions, _fixtures: Fixtures) -> FixtureContext[Path]:
    with tempfile.TemporaryDirectory() as tempdir:
        yield Path(tempdir)


@contextmanager
@depends("tmpdir")
def mock_environment(
    options: FixtureOptions, fixtures: Fixtures
) -> FixtureContext[dict[str, str]]:
    local_environ = options.get("environ", {})
    mock_environ = {
        "BUILD_PUBLISHER_API_KEY_ENABLE": "no",
        "BUILD_PUBLISHER_API_KEY_KEY": Fernet.generate_key().decode("ascii"),
        "BUILD_PUBLISHER_JENKINS_BASE_URL": "https://jenkins.invalid/",
        "BUILD_PUBLISHER_RECORDS_BACKEND": options["records_backend"],
        "BUILD_PUBLISHER_STORAGE_PATH": str(fixtures.tmpdir / "root"),
        "BUILD_PUBLISHER_WORKER_BACKEND": "sync",
        "BUILD_PUBLISHER_WORKER_THREAD_WAIT": "yes",
        **local_environ,
    }
    with mock.patch.dict(os.environ, mock_environ, clear=True):
        yield mock_environ


@depends("mock_environment")
def settings(_options: FixtureOptions, _fixtures: Fixtures) -> Settings:
    return Settings.from_environ()


@contextmanager
@depends("tmpdir")
def publisher(
    options: FixtureOptions, fixtures: Fixtures
) -> FixtureContext[BuildPublisher]:
    with mock_environment(options, fixtures):
        mock_publisher: BuildPublisher = BuildPublisherFactory()
        with _patch_publisher("jenkins", mock_publisher):
            with _patch_publisher("repo", mock_publisher):
                with _patch_publisher("storage", mock_publisher):
                    yield mock_publisher


@depends("publisher")
def gbp(options: FixtureOptions, _fixtures: Fixtures) -> GBP:
    user = options.get("user", "test_user")

    return test_gbp(
        "http://gbp.invalid/",
        auth={"user": user, "api_key": create_user_auth(user)},
    )


def console(_options: FixtureOptions, _fixtures: Fixtures) -> Fixtures:
    sc = string_console()

    return Fixtures(console=sc[0], stdout=sc[1], stderr=sc[2])


@depends("publisher")
def api_keys(options: FixtureOptions, fixtures: Fixtures) -> list[ApiKey]:
    names = options.get("api_key_names", ["test_api_key"])
    keys: list[ApiKey] = []

    for name in names:
        api_key = ApiKey(
            name=name, key=apikey.create_api_key(), created=time.localtime()
        )
        fixtures.publisher.repo.api_keys.save(api_key)
        keys.append(api_key)

    return keys


def records_db(options: FixtureOptions, _fixtures: Fixtures) -> RecordDB:
    [module] = importlib.metadata.entry_points(
        group="gentoo_build_publisher.records", name=options["records_backend"]
    )

    db: RecordDB = module.load().RecordDB()
    return db


def build_model(options: FixtureOptions, _fixtures: Fixtures) -> BuildModel:
    bm_options = options.get("build_model", {})
    built: dt.datetime = bm_options.get("built") or now()
    submitted: dt.datetime = bm_options.get("submitted") or now()
    completed: dt.datetime = bm_options.get("completed") or now()

    bm: BuildModel = BuildModelFactory.create(
        submitted=submitted,
        completed=completed,
        built=built,
    )
    return bm


@depends(records_db, build_model)
def record(options: FixtureOptions, fixtures: Fixtures) -> BuildRecord:
    record_options = options.get("record", {})
    bm: BuildModel = fixtures.build_model
    db: RecordDB = fixtures.records_db

    if logs := record_options.get("logs"):
        BuildLog.objects.create(build_model=bm, logs=logs)

    return db.get(Build.from_id(str(fixtures.build_model)))


def clock(options: FixtureOptions, _fixtures: Fixtures) -> dt.datetime:
    datetime: dt.datetime | None = options.get("clock")
    return datetime or now()


@depends("publisher")
def client(_options: FixtureOptions, _fixtures: Fixtures) -> Client:
    return Client()


def build(_options: FixtureOptions, _fixtures: Fixtures) -> Build:
    return BuildFactory()


def builds(
    options: FixtureOptions, _fixtures: Fixtures
) -> dict[str, list[Build]] | list[Build]:
    builds_options = options.get("builds", {})
    machines = builds_options.get("machines", ["babette"])
    end_date = builds_options.get("end_time", now())
    num_days = builds_options.get("num_days", 1)
    per_day = builds_options.get("per_day", 1)
    builds_map = BuildFactory.buncha_builds(machines, end_date, num_days, per_day)

    if len(machines) == 1:
        return builds_map[machines[0]]
    return builds_map


@depends(builds, publisher)
def pulled_builds(_options: FixtureOptions, fixtures: Fixtures) -> None:
    if isinstance(fixtures.builds, dict):
        builds_ = list(itertools.chain(*fixtures.builds.values()))
    else:
        builds_ = fixtures.builds

    for build_ in builds_:
        fixtures.publisher.pull(build_)


@depends(tmpdir)
def storage(_options: FixtureOptions, fixtures: Fixtures) -> Storage:
    root = fixtures.tmpdir / "root"
    return Storage(root)


@depends("tmpdir", "settings")
def jenkins(_options: FixtureOptions, fixtures: Fixtures) -> Jenkins:
    root = fixtures.tmpdir / "root"
    fixed_settings = replace(fixtures.settings, STORAGE_PATH=root)

    return MockJenkins.from_settings(fixed_settings)


@contextmanager
def _patch_publisher(name: str, mock_publisher: BuildPublisher) -> None:
    # pylint: disable=protected-access
    with mock.patch.object(publisher_mod._inst, name, getattr(mock_publisher, name)):
        with mock.patch.object(publisher_mod, name, getattr(mock_publisher, name)):
            yield


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


def add_funcs(test: BaseTestCase, funcs: Iterable[FixtureFunction]) -> None:
    for func in funcs:
        name = func.__name__.removesuffix("_fixture")
        if deps := getattr(func, "_deps", []):
            add_funcs(test, deps)
        if not hasattr(test.fixtures, name):
            setattr(test.fixtures, name, get_result(func, test))


def get_result(func: FixtureFunction, test: BaseTestCase) -> Any:
    result = func(test._options, copy.copy(test.fixtures))
    if hasattr(result, "__enter__") and hasattr(result, "__exit__"):
        result = test.enterContext(result)

    return result
