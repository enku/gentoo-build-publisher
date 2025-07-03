"""Tests for the GBP publisher"""

# pylint: disable=missing-docstring,unused-argument
import datetime as dt
from unittest import TestCase, mock
from zoneinfo import ZoneInfo

from unittest_fixtures import FixtureContext, Fixtures, fixture, given
from yarl import URL

import gbp_testkit.fixtures as testkit
from gbp_testkit.factories import BuildFactory, BuildRecordFactory
from gbp_testkit.helpers import BUILD_LOGS
from gentoo_build_publisher import publisher
from gentoo_build_publisher.build_publisher import BuildPublisher
from gentoo_build_publisher.records.memory import RecordDB
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.signals import dispatcher
from gentoo_build_publisher.types import Build, GBPMetadata, Package
from gentoo_build_publisher.utils.time import utctime


@given(testkit.tmpdir)
class BuildPublisherFromSettingsTestCase(TestCase):
    def test_from_settings_returns_publisher_with_given_settings(
        self, fixtures: Fixtures
    ) -> None:
        settings = Settings(
            JENKINS_BASE_URL="https://testserver.invalid/",
            RECORDS_BACKEND="memory",
            STORAGE_PATH=fixtures.tmpdir / "test_from_settings",
        )
        pub = BuildPublisher.from_settings(settings)

        self.assertEqual(
            pub.jenkins.config.base_url, URL("https://testserver.invalid/")
        )
        self.assertEqual(pub.storage.root, fixtures.tmpdir / "test_from_settings")
        self.assertIsInstance(pub.repo.build_records, RecordDB)


@given(testkit.build, testkit.publisher)
class BuildPublisherTestCase(TestCase):  # pylint: disable=too-many-public-methods
    def test_publish(self, fixtures: Fixtures) -> None:
        """.publish should publish the build artifact"""
        publisher.publish(fixtures.build)

        self.assertIs(publisher.storage.published(fixtures.build), True)

    def test_pull_without_db(self, fixtures: Fixtures) -> None:
        """pull creates db record and pulls from jenkins"""
        publisher.pull(fixtures.build)

        self.assertIs(publisher.storage.pulled(fixtures.build), True)
        self.assertIs(publisher.repo.build_records.exists(fixtures.build), True)

    def test_pull_stores_build_logs(self, fixtures: Fixtures) -> None:
        """Should store the logs of the build"""
        publisher.pull(fixtures.build)

        url = str(publisher.jenkins.url.logs(fixtures.build))
        publisher.jenkins.get_build_logs_mock_get.assert_called_once_with(url)

        record = publisher.record(fixtures.build)
        self.assertEqual(record.logs, BUILD_LOGS)

    def test_pull_updates_build_models_completed_field(
        self, fixtures: Fixtures
    ) -> None:
        """Should update the completed field with the current timestamp"""
        now = utctime()

        with mock.patch("gentoo_build_publisher.build_publisher.utctime") as mock_now:
            mock_now.return_value = now
            publisher.pull(fixtures.build)

        record = publisher.record(fixtures.build)
        self.assertEqual(record.completed, now)

    def test_pull_updates_build_models_built_field(self, fixtures: Fixtures) -> None:
        build = fixtures.build

        publisher.pull(build)

        record = publisher.record(build)

        jenkins_timestamp = dt.datetime.utcfromtimestamp(
            publisher.jenkins.artifact_builder.build_info(build).build_time / 1000
        ).replace(tzinfo=dt.UTC)
        self.assertEqual(record.built, jenkins_timestamp)

    def test_pull_does_not_download_when_already_pulled(
        self, fixtures: Fixtures
    ) -> None:
        build = fixtures.build

        publisher.pull(build)
        assert publisher.pulled(build)

        pulled = publisher.pull(build)

        self.assertFalse(pulled)

    def test_pulled_when_storage_is_ok_but_db_is_not(self, fixtures: Fixtures) -> None:
        # On rare occasion (server crash) the build appears to be extracted but the
        # record.completed field is None.  In this case Publisher.pulled(build) should
        # be False
        build = fixtures.build

        with mock.patch.object(
            publisher, "_update_build_metadata"
        ) as update_build_metadata:
            # _update_build_metadata sets the completed attribute
            update_build_metadata.return_value = None, None, None  # dummy values
            publisher.pull(build)

        self.assertFalse(publisher.pulled(build))

    def test_build_timestamps(self, fixtures: Fixtures) -> None:
        datetime = dt.datetime
        localtimezone = "gentoo_build_publisher.utils.time.LOCAL_TIMEZONE"

        with mock.patch(localtimezone, new=ZoneInfo("America/New_York")):
            submitted = datetime(2024, 1, 19, 11, 5, 49, tzinfo=dt.UTC)
            now = "gentoo_build_publisher.utils.time.now"
            with mock.patch(now, return_value=submitted):
                publisher.jenkins.artifact_builder.timer = (
                    1705662194  # 2024-01-19 11:03 UTC
                )
                build = BuildFactory()
                publisher.pull(build)
                record = publisher.record(build)

        ct = ZoneInfo("America/Chicago")
        self.assertEqual(record.built, datetime(2024, 1, 19, 5, 3, 24, tzinfo=ct))
        self.assertEqual(record.submitted, datetime(2024, 1, 19, 5, 5, 49, tzinfo=ct))
        self.assertEqual(record.completed, datetime(2024, 1, 19, 5, 5, 49, tzinfo=ct))

    def test_pull_with_note(self, fixtures: Fixtures) -> None:
        publisher.pull(fixtures.build, note="This is a test")

        self.assertIs(publisher.storage.pulled(fixtures.build), True)
        build_record = publisher.record(fixtures.build)
        self.assertEqual(build_record.note, "This is a test")

    def test_pull_with_tags(self, fixtures: Fixtures) -> None:
        build = fixtures.build
        tags = {"this", "is", "a", "test"}

        publisher.pull(build, tags=tags)

        self.assertIs(publisher.storage.pulled(build), True)
        self.assertEqual(set(publisher.tags(build)), tags)

    def test_update_build_metadata(self, fixtures: Fixtures) -> None:
        # pylint: disable=protected-access
        record = publisher.record(fixtures.build)

        publisher._update_build_metadata(record)

        record = publisher.record(fixtures.build)
        self.assertEqual(record.logs, BUILD_LOGS)
        self.assertIsNot(record.completed, None)

    def test_diff_binpkgs_should_be_empty_if_left_and_right_are_equal(
        self, fixtures: Fixtures
    ) -> None:
        left = fixtures.build
        publisher.get_packages = mock.Mock(wraps=publisher.get_packages)
        right = left

        # This should actually fail if not short-circuited because the builds have not
        # been pulled
        diff = [*publisher.diff_binpkgs(left, right)]

        self.assertEqual(diff, [])
        self.assertEqual(publisher.get_packages.call_count, 0)

    def test_tags_returns_the_list_of_tags_except_empty_tag(
        self, fixtures: Fixtures
    ) -> None:
        build = fixtures.build

        publisher.publish(build)
        publisher.storage.tag(build, "prod")

        self.assertEqual(publisher.storage.get_tags(build), ["", "prod"])
        self.assertEqual(publisher.tags(build), ["prod"])

    def test_tag_tags_the_build_at_the_storage_layer(self, fixtures: Fixtures) -> None:
        build = fixtures.build

        publisher.pull(build)
        publisher.tag(build, "prod")
        publisher.tag(build, "albert")

        self.assertEqual(publisher.storage.get_tags(build), ["albert", "prod"])

    def test_untag_removes_tag_from_the_build(self, fixtures: Fixtures) -> None:
        build = fixtures.build

        publisher.pull(build)
        publisher.tag(build, "prod")
        publisher.tag(build, "albert")

        publisher.untag(build.machine, "albert")

        self.assertEqual(publisher.storage.get_tags(build), ["prod"])

    def test_untag_with_empty_unpublishes_the_build(self, fixtures: Fixtures) -> None:
        build = fixtures.build

        publisher.publish(build)
        self.assertTrue(publisher.published(build))

        publisher.untag(build.machine, "")

        self.assertFalse(publisher.published(build))

    def test_save(self, fixtures: Fixtures) -> None:
        r1 = BuildRecordFactory()
        r2 = publisher.save(r1, note="This is a test")

        self.assertEqual(r2.note, "This is a test")

        r3 = publisher.record(Build(r1.machine, r1.build_id))
        self.assertEqual(r2, r3)

    def test_machines(self, fixtures: Fixtures) -> None:
        builds = [
            *BuildFactory.create_batch(3, machine="foo"),
            *BuildFactory.create_batch(2, machine="bar"),
            *BuildFactory.create_batch(1, machine="baz"),
        ]
        for build in builds:
            publisher.pull(build)

        machines = publisher.machines()

        self.assertEqual(len(machines), 3)

    def test_machines_with_filter(self, fixtures: Fixtures) -> None:
        builds = [
            *BuildFactory.create_batch(3, machine="foo"),
            *BuildFactory.create_batch(2, machine="bar"),
            *BuildFactory.create_batch(1, machine="baz"),
        ]
        for build in builds:
            publisher.pull(build)
        machines = publisher.machines(names={"bar", "baz", "bogus"})

        self.assertEqual(len(machines), 2)


@fixture()
def prepull_events(_fixtures: Fixtures) -> FixtureContext[list[Build]]:
    events: list[Build] = []

    def prepull(build: Build) -> None:
        events.append(build)

    dispatcher.bind(prepull=prepull)

    yield events


@fixture()
def postpull_events(
    _fixtures: Fixtures,
) -> FixtureContext[list[tuple[Build, list[Package], GBPMetadata | None]]]:
    events: list[tuple[Build, list[Package], GBPMetadata | None]] = []

    def postpull(
        *, build: Build, packages: list[Package], gbp_metadata: GBPMetadata | None
    ) -> None:
        events.append((build, packages, gbp_metadata))

    dispatcher.bind(postpull=postpull)

    yield events


@fixture()
def publish_events(_fixtures: Fixtures) -> FixtureContext[list[Build]]:
    events: list[Build] = []

    def publish(build: Build) -> None:
        events.append(build)

    dispatcher.bind(published=publish)

    yield events


@given(testkit.publisher, prepull_events, postpull_events, publish_events)
class DispatcherTestCase(TestCase):
    maxDiff = None

    def test_pull_single(self, fixtures: Fixtures) -> None:
        new_build = BuildFactory()
        publisher.pull(new_build)

        packages = publisher.storage.get_packages(new_build)
        expected = (
            publisher.record(new_build),
            packages,
            publisher.gbp_metadata(publisher.jenkins.get_metadata(new_build), packages),
        )
        self.assertEqual(fixtures.postpull_events, [expected])
        self.assertEqual(fixtures.prepull_events, [new_build])

    def test_pull_multi(self, fixtures: Fixtures) -> None:
        build1 = BuildFactory()
        build2 = BuildFactory(machine="fileserver")
        publisher.pull(build1)
        publisher.pull(build2)

        record1 = publisher.record(build1)
        record2 = publisher.record(build2)

        packages = publisher.storage.get_packages(record1)
        event1 = (
            record1,
            packages,
            publisher.gbp_metadata(publisher.jenkins.get_metadata(record1), packages),
        )
        packages = publisher.storage.get_packages(record2)
        event2 = (
            record2,
            packages,
            publisher.gbp_metadata(publisher.jenkins.get_metadata(record2), packages),
        )
        self.assertEqual(fixtures.prepull_events, [build1, build2])
        self.assertEqual(fixtures.postpull_events, [event1, event2])

    def test_publish(self, fixtures: Fixtures) -> None:
        new_build = BuildFactory()
        publisher.publish(new_build)

        record = publisher.record(new_build)
        self.assertEqual(fixtures.publish_events, [record])


@fixture()
def builds_fixture(_fixtures: Fixtures) -> list[Build]:
    # So for this case let's say we have 4 builds.  None have built timestamps.  The
    # 3rd one is published (but has no built timestamp) and the first 2 are pulled
    # but not published:
    builds: list[Build] = BuildFactory.create_batch(4)
    return builds


@given(testkit.publisher)
class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self, fixtures: Fixtures) -> None:
        response = publisher.schedule_build("babette")

        self.assertEqual("https://jenkins.invalid/job/babette/build", response)
        self.assertEqual(publisher.jenkins.scheduled_builds, ["babette"])
