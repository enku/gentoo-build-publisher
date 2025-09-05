"""Fixtures"""

# pylint: disable=missing-docstring,redefined-outer-name
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
from django.conf import settings as django_settings
from django.test.client import Client
from gbpcli.gbp import GBP
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

from .factories import (
    BuildFactory,
    BuildModelFactory,
    BuildPublisherFactory,
    BuildRecordFactory,
)
from .helpers import MockJenkins, TestConsole, create_user_auth, make_gbpcli, test_gbp

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
    """Override os.environ

    When the clear parameter is True, the os.environ is replaced with an empty Mapping.
    Pass overrides in the environ parameter.
    """
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
    """Creates a gentoo_build_publisher.settings.Settings object

    This is instantiated from the environment variables. As such this fixture uses the
    environ fixture.
    """
    return Settings.from_environ()


@fixture(environ)
def publisher(_fixtures: Fixtures) -> FixtureContext[BuildPublisher]:
    """This replaces gentoo_build_publisher.publisher with a test-able fixture

    Specifically it overrides the `jenkins`, `repo`, and `storage` attributes.

    The storage root points to a temporary directory (in fixtures.tmpdir).
    The jenkins attribute is a MockJenkins instance.
    The repo attribute is a memory backend.
    """
    bp: BuildPublisher = BuildPublisherFactory()

    @contextmanager
    def pp(name: str) -> FixtureContext[None]:
        with mock.patch.object(
            gentoo_build_publisher.publisher, name, getattr(bp, name)
        ):
            yield

    with pp("jenkins"), pp("repo"), pp("storage"):
        yield bp


@fixture()
def allowed_host(_: Fixtures, allowed_host: str = "testserver") -> FixtureContext[None]:
    """Add the host to settings.ALLOWED_HOSTS

    For the allowed_host "testserver", the default, this is automatically done by the
    Django test runner. But we are not always using the Django test runner.
    """
    hosts = [*django_settings.ALLOWED_HOSTS, allowed_host]

    with mock.patch.object(django_settings, "ALLOWED_HOSTS", hosts):
        yield


@fixture(publisher, allowed_host)
def gbp(_fixtures: Fixtures, user: str = "test_user") -> GBP:
    """Returns a testable GBP instance.

    This instance calls the /graphql Django view directly so no server is needed.
    """
    return test_gbp(
        "http://gbp.invalid/", auth={"user": user, "api_key": create_user_auth(user)}
    )


@fixture()
def console(_fixtures: Fixtures) -> FixtureContext[TestConsole]:
    """Returns a `TestConsole` instance"""
    c = TestConsole()

    yield c

    if "SAVE_VIRTUAL_CONSOLE" in os.environ:
        global COUNTER  # pylint: disable=global-statement

        COUNTER += 1
        filename = f"{COUNTER}.svg"
        c.out.save_svg(filename, title="Gentoo Build Publisher")


@fixture(console, gbp)
def gbpcli(fixtures: Fixtures) -> Callable[[str], int]:
    """A function that you can pass a gbpcli command line to
    Also adds the gbp and console fixtures to the TestCase.

    e.g.

    >>> @given(gbpcli)
    >>> class MyTests(TestCase):
    ...     def test(self, fixtures):
    ...         fixtures.gbpcli("gbp list babette")
    ...         output = fixtures.console.out.getvalue()
    """
    return make_gbpcli(fixtures.gbp, fixtures.console)


@fixture(publisher)
def api_keys(fixtures: Fixtures, names: list[str] | None = None) -> list[ApiKey]:
    """Given the names, returns a list of ApiKeys created in the test BuildPublisher"""
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
    """A RecordDB instance

    Defaults to a memory backend instance. This can be overridden with the `backend`
    parameter.
    """
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


@fixture()
def build_record(
    _fixtures: Fixtures,
    built: dt.datetime | None = None,
    submitted: dt.datetime | None = None,
    completed: dt.datetime | None = None,
) -> BuildRecord:
    """Record-only equivalent to build_model.

    This is backend-independent and thus not saved to a backend.  However you can do
    something like:

        >>> @given(saved_record=lambda f: f.records_db.save(f.build_record))
        >>> @given(build_record, records_db)
        >>> class MyTest(TestCase): ...
    """
    built = built or now()
    submitted = submitted or now()
    completed = completed or now()

    record: BuildRecord = BuildRecordFactory(
        submitted=submitted, completed=completed, built=built
    )
    return record


@fixture(records_db, build_model)
def record(fixtures: Fixtures, logs: str = "") -> BuildRecord:
    """A BuildRecord saved to a django backend

    This is deprecated. It is recommended to use build_record and records_db fixtures
    instead.
    """
    bm: BuildModel = fixtures.build_model
    db: RecordDB = fixtures.records_db

    if logs:
        BuildLog.objects.create(build_model=bm, logs=logs)

    return db.get(Build.from_id(str(fixtures.build_model)))


@fixture()
def clock(_fixtures: Fixtures, clock: dt.datetime | None = None) -> dt.datetime:
    """A datetime instance

    The value defaults to the .now()
    """
    return clock if clock else now()


@fixture(publisher)
def client(_fixtures: Fixtures) -> Client:
    """A Django test Client"""
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
    """Creates Builds and returns them in a list or dict of lists

    If the `machines` parameter has a single entry, returns a list of Builds.

    If the `machines` parameter does not have a single entry, returns a dict of
    [machine, list[Build].

    num_days are the number of days to create builds for.
    per_day is the number of builds (per machine) to create on a given day.
    end_time is the submitted timestamp of the last build (per machine)
    """
    if machines is None:
        machines = ["babette"]
    end_time = end_time or now()
    builds_map = BuildFactory.buncha_builds(machines, end_time, num_days, per_day)

    if len(machines) == 1:
        return builds_map[machines[0]]
    return builds_map


@fixture(builds, publisher)
def pulled_builds(fixtures: Fixtures) -> None:
    """Uses the builds fixture and pulls all of builds"""
    if isinstance(fixtures.builds, dict):
        builds_ = list(itertools.chain(*fixtures.builds.values()))
    else:
        builds_ = fixtures.builds

    for build_ in builds_:
        fixtures.publisher.pull(build_)


@fixture(tmpdir)
def storage(fixtures: Fixtures) -> Storage:
    """A Storage instance

    Uses the tmpdir fixture and roots the Storage in tmpdir/root
    """
    root = fixtures.tmpdir / "root"
    return Storage(root)


@fixture(tmpdir, settings)
def jenkins(fixtures: Fixtures) -> Jenkins:
    """A MockJenkins instance"""
    root = fixtures.tmpdir / "root"
    fixed_settings = replace(fixtures.settings, STORAGE_PATH=root)

    return MockJenkins.from_settings(fixed_settings)


@fixture()
def plugins(
    _fixtures: Fixtures, plugins: Iterable[str] = ("foo", "bar", "baz")
) -> FixtureContext[list[Plugin]]:
    """Mocks the get_plugins function to return a fake list of Plugins"""
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
def patch(  # pylint: disable=redefined-builtin
    _: Fixtures, target: str = "", object: Any = _NO_OBJECT, **kwargs: Any
) -> FixtureContext[Any]:
    """mock.patch on steroids

    This is a fixture for mock.patch, mock.patch.object and mock.Mock

    All **kwargs are passed to the respective initializer.

    When no target is specified, returns a Mock instance.

    When target is specified, mock's the given target. The replacement depends on
    **kwargs.

    When object is specified, mock's the given target on the given object. The
    replacement depends on **kwargs.
    """
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
