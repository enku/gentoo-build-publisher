"""Fixtures"""

# pylint: disable=missing-docstring,redefined-outer-name
import datetime as dt
import importlib.metadata
import io
import itertools
import os
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any, Iterable
from unittest import mock

import rich.console
from cryptography.fernet import Fernet
from django.test.client import Client
from gbpcli.gbp import GBP
from gbpcli.theme import DEFAULT_THEME
from gbpcli.types import Console
from rich.theme import Theme
from unittest_fixtures import FixtureContext, Fixtures, fixture

import gentoo_build_publisher
from gentoo_build_publisher.build_publisher import BuildPublisher
from gentoo_build_publisher.cli import apikey
from gentoo_build_publisher.django.gentoo_build_publisher.models import (
    BuildLog,
    BuildModel,
)
from gentoo_build_publisher.jenkins import Jenkins
from gentoo_build_publisher.plugins import Plugin
from gentoo_build_publisher.records import BuildRecord, RecordDB
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage
from gentoo_build_publisher.types import ApiKey, Build
from gentoo_build_publisher.utils import time

from .factories import BuildFactory, BuildModelFactory, BuildPublisherFactory
from .helpers import MockJenkins, create_user_auth, test_gbp

COUNTER = 0
_NO_OBJECT = object()
now = partial(dt.datetime.now, tz=dt.UTC)


@fixture()
def tmpdir(_fixtures: Fixtures) -> FixtureContext[Path]:
    with tempfile.TemporaryDirectory() as tempdir:
        yield Path(tempdir)


@fixture(tmpdir)
def environ(
    fixtures: Fixtures, environ: dict[str, str] | None = None, clear: bool = False
) -> FixtureContext[dict[str, str]]:
    environ = environ or {}
    mock_environ = {
        "BUILD_PUBLISHER_API_KEY_ENABLE": "no",
        "BUILD_PUBLISHER_API_KEY_KEY": Fernet.generate_key().decode("ascii"),
        "BUILD_PUBLISHER_JENKINS_BASE_URL": "https://jenkins.invalid/",
        "BUILD_PUBLISHER_RECORDS_BACKEND": "memory",
        "BUILD_PUBLISHER_STORAGE_PATH": str(fixtures.tmpdir / "root"),
        "BUILD_PUBLISHER_WORKER_BACKEND": "sync",
        "BUILD_PUBLISHER_WORKER_THREAD_WAIT": "yes",
        **environ,
    }
    with mock.patch.dict(os.environ, mock_environ, clear=clear):
        yield mock_environ


@fixture(environ)
def settings(_fixtures: Fixtures) -> Settings:
    return Settings.from_environ()


@fixture(environ)
def publisher(_fixtures: Fixtures) -> FixtureContext[BuildPublisher]:
    bp: BuildPublisher = BuildPublisherFactory()

    @contextmanager
    def pp(name: str) -> FixtureContext[None]:
        with mock.patch.object(
            gentoo_build_publisher.publisher, name, getattr(bp, name)
        ):
            yield

    with pp("jenkins"), pp("repo"), pp("storage"):
        yield bp


@fixture(publisher)
def gbp(_fixtures: Fixtures, user: str = "test_user") -> GBP:
    return test_gbp(
        "http://gbp.invalid/", auth={"user": user, "api_key": create_user_auth(user)}
    )


@fixture()
def console(_fixtures: Fixtures) -> FixtureContext[Console]:
    out = io.StringIO()
    err = io.StringIO()
    theme = Theme(DEFAULT_THEME)

    c = Console(
        out=rich.console.Console(
            file=out, width=88, theme=theme, highlight=False, record=True
        ),
        err=rich.console.Console(file=err, width=88, record=True),
    )
    yield c

    if "SAVE_VIRTUAL_CONSOLE" in os.environ:
        global COUNTER  # pylint: disable=global-statement

        COUNTER += 1
        filename = f"{COUNTER}.svg"
        c.out.save_svg(filename, title="Gentoo Build Publisher")


@fixture(publisher)
def api_keys(fixtures: Fixtures, names: list[str] | None = None) -> list[ApiKey]:
    if names is None:
        names = ["test_api_key"]
    keys: list[ApiKey] = []

    for name in names:
        api_key = ApiKey(
            name=name, key=apikey.create_api_key(), created=time.localtime()
        )
        fixtures.publisher.repo.api_keys.save(api_key)
        keys.append(api_key)

    return keys


@fixture()
def records_db(_fixtures: Fixtures, backend: str = "memory") -> RecordDB:
    [module] = importlib.metadata.entry_points(
        group="gentoo_build_publisher.records", name=backend
    )

    db: RecordDB = module.load().RecordDB()
    return db


@fixture()
def build_model(
    _fixtures: Fixtures,
    built: dt.datetime | None = None,
    submitted: dt.datetime | None = None,
    completed: dt.datetime | None = None,
) -> BuildModel:
    built = built or now()
    submitted = submitted or now()
    completed = completed or now()

    bm: BuildModel = BuildModelFactory.create(
        submitted=submitted, completed=completed, built=built
    )
    return bm


@fixture(records_db, build_model)
def record(fixtures: Fixtures, logs: str = "") -> BuildRecord:
    bm: BuildModel = fixtures.build_model
    db: RecordDB = fixtures.records_db

    if logs:
        BuildLog.objects.create(build_model=bm, logs=logs)

    return db.get(Build.from_id(str(fixtures.build_model)))


@fixture()
def clock(_fixtures: Fixtures, clock: dt.datetime | None = None) -> dt.datetime:
    return clock if clock else now()


@fixture(publisher)
def client(_fixtures: Fixtures) -> Client:
    return Client()


@fixture()
def build(_fixtures: Fixtures, machine: str = "babette") -> Build:
    return BuildFactory(machine=machine)


@fixture()
def builds(
    _fixtures: Fixtures,
    machines: list[str] | None = None,
    end_time: dt.datetime | None = None,
    num_days: int = 1,
    per_day: int = 1,
) -> dict[str, list[Build]] | list[Build]:
    if machines is None:
        machines = ["babette"]
    end_time = end_time or now()
    builds_map = BuildFactory.buncha_builds(machines, end_time, num_days, per_day)

    if len(machines) == 1:
        return builds_map[machines[0]]
    return builds_map


@fixture(builds, publisher)
def pulled_builds(fixtures: Fixtures) -> None:
    if isinstance(fixtures.builds, dict):
        builds_ = list(itertools.chain(*fixtures.builds.values()))
    else:
        builds_ = fixtures.builds

    for build_ in builds_:
        fixtures.publisher.pull(build_)


@fixture(tmpdir)
def storage(fixtures: Fixtures) -> Storage:
    root = fixtures.tmpdir / "root"
    return Storage(root)


@fixture(tmpdir, settings)
def jenkins(fixtures: Fixtures) -> Jenkins:
    root = fixtures.tmpdir / "root"
    fixed_settings = replace(fixtures.settings, STORAGE_PATH=root)

    return MockJenkins.from_settings(fixed_settings)


@fixture()
def plugins(
    _fixtures: Fixtures, plugins: Iterable[str] = ("foo", "bar", "baz")
) -> FixtureContext[list[Plugin]]:
    plist = [
        Plugin(
            app=f"test.plugin.{i}",
            description=f"Plugin for {i}",
            graphql=None,
            name=i,
            urls=None,
        )
        for i in plugins
    ]
    with mock.patch("gentoo_build_publisher.plugins.get_plugins") as gp:
        gp.return_value = plist
        yield plist


@fixture()
def patch(
    _: Fixtures,
    target: str = "",
    object: Any = _NO_OBJECT,  # pylint: disable=redefined-builtin
    attrs: dict[str, Any] | None = None,
    **kwargs: Any,
) -> FixtureContext[mock.Mock]:
    attrs = attrs or {}

    if not target:
        patcher = None
        fake = mock.Mock(**kwargs)
    elif object is _NO_OBJECT:
        patcher = mock.patch(target, **kwargs)
        fake = patcher.start()
    else:
        patcher = mock.patch.object(object, target, **kwargs)
        fake = patcher.start()

    yield fake

    if patcher:
        patcher.stop()
