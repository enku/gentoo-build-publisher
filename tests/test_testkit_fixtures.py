# pylint: disable=missing-docstring,unused-argument
import datetime as dt
import os
from pathlib import Path
from unittest import TestCase

from django.conf import settings as django_settings
from django.test import TestCase as DjangoTestCase
from unittest_fixtures import FixtureContext, Fixtures, fixture, given, where

import gbp_testkit.fixtures as testkit
from gentoo_build_publisher import publisher


@fixture(testkit.tmpdir)
def cd(fixtures: Fixtures) -> FixtureContext[Path]:
    """Changes to the given directory (tmpdir by default)"""
    cwd = cwd = os.getcwd()
    os.chdir(fixtures.tmpdir)
    yield fixtures.tmpdir
    os.chdir(cwd)


class TmpdirTests(TestCase):
    def test(self) -> None:
        tmpdir = None

        @given(testkit.tmpdir)
        class MyTest(TestCase):
            def test_it(self, fixtures: Fixtures) -> None:
                nonlocal tmpdir
                tmpdir = fixtures.tmpdir
                self.assertTrue(tmpdir.is_dir())

        result = MyTest("test_it").run()
        assert result
        self.assertFalse(result.failures)
        self.assertFalse(result.errors)
        assert tmpdir
        self.assertFalse(tmpdir.is_dir())


class EnvironTests(TestCase):
    def test(self) -> None:
        self.assertNotIn("ENVIRON_TEST", os.environ)

        @given(testkit.environ)
        @where(environ={"ENVIRON_TEST": "yes"})
        class MyTest(TestCase):
            def test_it(self, fixtures: Fixtures) -> None:
                self.assertEqual(os.environ["ENVIRON_TEST"], "yes")

        result = MyTest("test_it").run()
        assert result
        self.assertFalse(result.failures)
        self.assertFalse(result.errors)
        self.assertNotIn("ENVIRON_TEST", os.environ)


@given(testkit.settings)
@where(environ={"BUILD_PUBLISHER_JENKINS_BASE_URL": "blablabla"})
class SettingsTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        self.assertEqual(fixtures.settings.JENKINS_BASE_URL, "blablabla")


@given(testkit.publisher, testkit.tmpdir)
class PublisherTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        tmpdir = fixtures.tmpdir

        self.assertEqual("MockJenkins", type(publisher.jenkins).__name__)
        self.assertEqual(tmpdir / "root", publisher.storage.root)


@given(testkit.gbp)
class GBPTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        gbp = fixtures.gbp
        gbp.machine_names()


@given(testkit.gbpcli)
class GBPCLITests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        self.assertEqual(fixtures.gbpcli("gbp check"), 0)


@given(testkit.tmpdir, testkit.environ, cd)
@where(environ={"SAVE_VIRTUAL_CONSOLE": "1"})
class ConsoleTestsWithSave(TestCase):
    def test_having_save_enabled(self, fixtures: Fixtures) -> None:
        @given(testkit.console)
        class MyTest(TestCase):
            def test_it(self, fixtures: Fixtures) -> None:
                console = fixtures.console
                console.out.print("Hello world!")
                self.assertEqual("Hello world!\n", console.out.file.getvalue())

        result = MyTest("test_it").run()
        assert result
        self.assertFalse(result.failures)
        self.assertFalse(result.errors)

        screenshots = list(fixtures.tmpdir.glob("*.svg"))
        self.assertEqual(len(screenshots), 1)


@given(testkit.tmpdir, testkit.environ, cd)
class ConsoleTestsWithoutSave(TestCase):
    def test_having_save_disabled(self, fixtures: Fixtures) -> None:
        os.environ.pop("SAVE_VIRTUAL_CONSOLE", None)

        @given(testkit.console)
        class MyTest(TestCase):
            def test_it(self, fixtures: Fixtures) -> None:
                console = fixtures.console
                console.out.print("Hello world!")

        result = MyTest("test_it").run()
        assert result
        self.assertFalse(result.failures)
        self.assertFalse(result.errors)

        screenshots = list(fixtures.tmpdir.glob("*.svg"))
        self.assertEqual(len(screenshots), 0)


@given(testkit.api_keys)
@where(api_keys__names=["ApiKey1", "TestKey2", "PlaceholderKey3", "TestKey4"])
class APIKeysTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        api_keys = fixtures.api_keys
        key_names = [i.name for i in api_keys]
        self.assertEqual(
            ["ApiKey1", "TestKey2", "PlaceholderKey3", "TestKey4"], key_names
        )


@given(testkit.records_db)
class RecordsDBTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        records_db = fixtures.records_db
        self.assertEqual("RecordDB", type(records_db).__name__)


@given(testkit.build_model)
class BuildModelTests(DjangoTestCase):
    def test(self, fixtures: Fixtures) -> None:
        build_model = fixtures.build_model
        self.assertEqual("BuildModel", type(build_model).__name__)


@given(testkit.record)
@where(records_db__backend="django", record__logs="test")
class RecordTests(DjangoTestCase):
    def test(self, fixtures: Fixtures) -> None:
        record = fixtures.record
        self.assertEqual("BuildRecord", type(record).__name__)
        self.assertEqual("test", record.logs)


@given(testkit.clock)
class ClockTestsNow(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        now = dt.datetime.now(tz=dt.UTC)
        self.assertLessEqual(fixtures.clock, now)


@given(testkit.clock)
@where(clock=dt.datetime(2038, 1, 19, 3, 14, 7, tzinfo=dt.UTC))
class ClockTestsNowPassedParam(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        self.assertEqual(
            fixtures.clock, dt.datetime(2038, 1, 19, 3, 14, 7, tzinfo=dt.UTC)
        )


@given(testkit.client)
class ClientTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        self.assertEqual("Client", type(client).__name__)

        response = client.get("/")
        self.assertEqual(response.status_code, 200)


@given(testkit.build)
class BuildTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        build = fixtures.build
        self.assertEqual("Build", type(build).__name__)


@given(testkit.builds)
@where(
    builds__machines=["ApiKey1", "TestKey2", "PlaceholderKey3", "TestKey4"],
    builds__num_days=7,
)
class BuildsTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        builds = fixtures.builds
        self.assertEqual(4, len(builds))

        for v in builds.values():
            self.assertEqual(7, len(v))


@given(testkit.pulled_builds, testkit.publisher)
@where(builds__num_days=7)
class PulledBuildsTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        self.assertEqual(7, publisher.repo.build_records.count())


@given(testkit.storage)
class StorageTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        storage = fixtures.storage
        self.assertEqual("Storage", type(storage).__name__)


@given(testkit.jenkins)
class JenkinsTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        jenkins = fixtures.jenkins
        self.assertEqual("MockJenkins", type(jenkins).__name__)


@given(testkit.allowed_host)
@where(allowed_host="foobar")
class AllowedHostTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        self.assertEqual(django_settings.ALLOWED_HOSTS[-1], "foobar")
