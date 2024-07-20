"""Tests for the GBP publisher"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
from unittest import mock
from zoneinfo import ZoneInfo

from yarl import URL

from gentoo_build_publisher import publisher
from gentoo_build_publisher.records.memory import RecordDB
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.signals import dispatcher
from gentoo_build_publisher.types import Build, Content, GBPMetadata, Package
from gentoo_build_publisher.utils.time import utctime

from . import TestCase
from .factories import BuildFactory, BuildRecordFactory
from .fixture import (
    BaseTestCase,
    FixtureContext,
    FixtureOptions,
    Fixtures,
    depends,
    requires,
)
from .helpers import BUILD_LOGS


@requires("tmpdir")
class BuildPublisherFromSettingsTestCase(BaseTestCase):
    def test_from_settings_returns_publisher_with_given_settings(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="https://testserver.invalid/",
            RECORDS_BACKEND="memory",
            STORAGE_PATH=self.fixtures.tmpdir / "test_from_settings",
        )
        pub = publisher.BuildPublisher.from_settings(settings)

        self.assertEqual(
            pub.jenkins.config.base_url, URL("https://testserver.invalid/")
        )
        self.assertEqual(pub.storage.root, self.fixtures.tmpdir / "test_from_settings")
        self.assertIsInstance(pub.repo.build_records, RecordDB)


@requires("build", "publisher")
class BuildPublisherTestCase(TestCase):  # pylint: disable=too-many-public-methods
    def test_publish(self) -> None:
        """.publish should publish the build artifact"""
        self.fixtures.publisher.publish(self.fixtures.build)

        self.assertIs(
            self.fixtures.publisher.storage.published(self.fixtures.build), True
        )

    def test_pull_without_db(self) -> None:
        """pull creates db record and pulls from jenkins"""
        self.fixtures.publisher.pull(self.fixtures.build)

        self.assertIs(self.fixtures.publisher.storage.pulled(self.fixtures.build), True)
        self.assertIs(
            self.fixtures.publisher.repo.build_records.exists(self.fixtures.build),
            True,
        )

    def test_pull_stores_build_logs(self) -> None:
        """Should store the logs of the build"""
        self.fixtures.publisher.pull(self.fixtures.build)

        url = str(self.fixtures.publisher.jenkins.url.logs(self.fixtures.build))
        self.fixtures.publisher.jenkins.get_build_logs_mock_get.assert_called_once_with(
            url
        )

        record = self.fixtures.publisher.record(self.fixtures.build)
        self.assertEqual(record.logs, BUILD_LOGS)

    def test_pull_updates_build_models_completed_field(self) -> None:
        """Should update the completed field with the current timestamp"""
        now = utctime()

        with mock.patch("gentoo_build_publisher.publisher.utctime") as mock_now:
            mock_now.return_value = now
            self.fixtures.publisher.pull(self.fixtures.build)

        record = self.fixtures.publisher.record(self.fixtures.build)
        self.assertEqual(record.completed, now)

    def test_pull_updates_build_models_built_field(self) -> None:
        self.fixtures.publisher.pull(self.fixtures.build)

        record = self.fixtures.publisher.record(self.fixtures.build)

        jenkins_timestamp = dt.datetime.utcfromtimestamp(
            self.fixtures.publisher.jenkins.artifact_builder.build_info(
                self.fixtures.build
            ).build_time
            / 1000
        ).replace(tzinfo=dt.UTC)
        self.assertEqual(record.built, jenkins_timestamp)

    def test_pull_does_not_download_when_already_pulled(self) -> None:
        self.fixtures.publisher.pull(self.fixtures.build)
        assert self.fixtures.publisher.pulled(self.fixtures.build)

        pulled = self.fixtures.publisher.pull(self.fixtures.build)

        self.assertFalse(pulled)

    def test_pulled_when_storage_is_ok_but_db_is_not(self) -> None:
        # On rare occasion (server crash) the build appears to be extracted but the
        # record.completed field is None.  In this case Publisher.pulled(build) should
        # be False
        with mock.patch.object(
            self.fixtures.publisher, "_update_build_metadata"
        ) as update_build_metadata:
            # _update_build_metadata sets the completed attribute
            update_build_metadata.return_value = None, None, None  # dummy values
            self.fixtures.publisher.pull(self.fixtures.build)

        self.assertFalse(self.fixtures.publisher.pulled(self.fixtures.build))

    def test_build_timestamps(self) -> None:
        localtimezone = "gentoo_build_publisher.utils.time.LOCAL_TIMEZONE"
        with mock.patch(localtimezone, new=ZoneInfo("America/New_York")):
            submitted = dt.datetime(2024, 1, 19, 11, 5, 49, tzinfo=dt.UTC)
            now = "gentoo_build_publisher.utils.time.now"
            with mock.patch(now, return_value=submitted):
                self.fixtures.publisher.jenkins.artifact_builder.timer = (
                    1705662194  # 2024-01-19 11:03 UTC
                )
                build = BuildFactory()
                self.fixtures.publisher.pull(build)
                record = self.fixtures.publisher.record(build)

        ct = ZoneInfo("America/Chicago")
        self.assertEqual(record.built, dt.datetime(2024, 1, 19, 5, 3, 24, tzinfo=ct))
        self.assertEqual(
            record.submitted, dt.datetime(2024, 1, 19, 5, 5, 49, tzinfo=ct)
        )
        self.assertEqual(
            record.completed, dt.datetime(2024, 1, 19, 5, 5, 49, tzinfo=ct)
        )

    def test_pull_with_note(self) -> None:
        self.fixtures.publisher.pull(self.fixtures.build, note="This is a test")

        self.assertIs(self.fixtures.publisher.storage.pulled(self.fixtures.build), True)
        build_record = self.fixtures.publisher.record(self.fixtures.build)
        self.assertEqual(build_record.note, "This is a test")

    def test_pull_with_tags(self) -> None:
        tags = {"this", "is", "a", "test"}

        self.fixtures.publisher.pull(self.fixtures.build, tags=tags)

        self.assertIs(self.fixtures.publisher.storage.pulled(self.fixtures.build), True)
        self.assertEqual(set(self.fixtures.publisher.tags(self.fixtures.build)), tags)

    def test_purge_deletes_old_build(self) -> None:
        """Should remove purgeable builds"""
        old_build = self.fixtures.build
        self.fixtures.publisher.pull(old_build)
        record = self.fixtures.publisher.record(old_build)
        self.fixtures.publisher.repo.build_records.save(
            record, submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
        )

        new_build = BuildFactory()
        self.fixtures.publisher.pull(new_build)
        record = self.fixtures.publisher.record(new_build)
        self.fixtures.publisher.repo.build_records.save(
            record, submitted=dt.datetime(1970, 12, 31, tzinfo=dt.UTC)
        )

        self.fixtures.publisher.purge(old_build.machine)

        self.assertIs(
            self.fixtures.publisher.repo.build_records.exists(old_build), False
        )

        for item in Content:
            path = self.fixtures.publisher.storage.get_path(old_build, item)
            self.assertIs(path.exists(), False, path)

    def test_purge_does_not_delete_old_tagged_builds(self) -> None:
        """Should remove purgeable builds"""

        kept_build = BuildFactory(machine="lighthouse")
        self.fixtures.publisher.repo.build_records.save(
            self.fixtures.publisher.record(kept_build),
            submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC),
            keep=True,
        )
        tagged_build = BuildFactory(machine="lighthouse")
        self.fixtures.publisher.repo.build_records.save(
            self.fixtures.publisher.record(tagged_build),
            submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC),
        )
        self.fixtures.publisher.pull(tagged_build)
        self.fixtures.publisher.tag(tagged_build, "prod")
        self.fixtures.publisher.repo.build_records.save(
            self.fixtures.publisher.record(BuildFactory(machine="lighthouse")),
            submitted=dt.datetime(1970, 12, 31, tzinfo=dt.UTC),
        )

        self.fixtures.publisher.purge("lighthouse")

        self.assertIs(
            self.fixtures.publisher.repo.build_records.exists(kept_build), True
        )
        self.assertIs(
            self.fixtures.publisher.repo.build_records.exists(tagged_build), True
        )

    def test_purge_doesnt_delete_old_published_build(self) -> None:
        """Should not delete old build if published"""
        self.fixtures.publisher.publish(self.fixtures.build)
        self.fixtures.publisher.repo.build_records.save(
            self.fixtures.publisher.record(self.fixtures.build),
            submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC),
        )
        self.fixtures.publisher.repo.build_records.save(
            self.fixtures.publisher.record(BuildFactory()),
            submitted=dt.datetime(1970, 12, 31, tzinfo=dt.UTC),
        )

        self.fixtures.publisher.purge(self.fixtures.build.machine)

        self.assertIs(
            self.fixtures.publisher.repo.build_records.exists(self.fixtures.build),
            True,
        )

    def test_update_build_metadata(self) -> None:
        # pylint: disable=protected-access
        record = self.fixtures.publisher.record(self.fixtures.build)

        self.fixtures.publisher._update_build_metadata(record)

        record = self.fixtures.publisher.record(self.fixtures.build)
        self.assertEqual(record.logs, BUILD_LOGS)
        self.assertIsNot(record.completed, None)

    def test_diff_binpkgs_should_be_empty_if_left_and_right_are_equal(self) -> None:
        left = self.fixtures.build
        self.fixtures.publisher.get_packages = mock.Mock(
            wraps=self.fixtures.publisher.get_packages
        )
        right = left

        # This should actually fail if not short-circuited because the builds have not
        # been pulled
        diff = [*publisher.diff_binpkgs(left, right)]

        self.assertEqual(diff, [])
        self.assertEqual(self.fixtures.publisher.get_packages.call_count, 0)

    def test_tags_returns_the_list_of_tags_except_empty_tag(self) -> None:
        self.fixtures.publisher.publish(self.fixtures.build)
        self.fixtures.publisher.storage.tag(self.fixtures.build, "prod")

        self.assertEqual(
            self.fixtures.publisher.storage.get_tags(self.fixtures.build),
            ["", "prod"],
        )
        self.assertEqual(self.fixtures.publisher.tags(self.fixtures.build), ["prod"])

    def test_tag_tags_the_build_at_the_storage_layer(self) -> None:
        self.fixtures.publisher.pull(self.fixtures.build)
        self.fixtures.publisher.tag(self.fixtures.build, "prod")
        self.fixtures.publisher.tag(self.fixtures.build, "albert")

        self.assertEqual(
            publisher.storage.get_tags(self.fixtures.build), ["albert", "prod"]
        )

    def test_untag_removes_tag_from_the_build(self) -> None:
        self.fixtures.publisher.pull(self.fixtures.build)
        self.fixtures.publisher.tag(self.fixtures.build, "prod")
        self.fixtures.publisher.tag(self.fixtures.build, "albert")

        self.fixtures.publisher.untag(self.fixtures.build.machine, "albert")

        self.assertEqual(
            self.fixtures.publisher.storage.get_tags(self.fixtures.build),
            ["prod"],
        )

    def test_untag_with_empty_unpublishes_the_build(self) -> None:
        self.fixtures.publisher.publish(self.fixtures.build)
        self.assertTrue(self.fixtures.publisher.published(self.fixtures.build))

        self.fixtures.publisher.untag(self.fixtures.build.machine, "")

        self.assertFalse(self.fixtures.publisher.published(self.fixtures.build))

    def test_save(self) -> None:
        r1 = BuildRecordFactory()
        r2 = publisher.save(r1, note="This is a test")

        self.assertEqual(r2.note, "This is a test")

        r3 = publisher.record(Build(r1.machine, r1.build_id))
        self.assertEqual(r2, r3)


def prepull_events(
    _options: FixtureOptions, _fixtures: Fixtures
) -> FixtureContext[list[Build]]:
    events: list[Build] = []

    def prepull(build: Build) -> None:
        events.append(build)

    dispatcher.bind(prepull=prepull)

    yield events


def postpull_events(
    _options: FixtureOptions, _fixtures: Fixtures
) -> FixtureContext[list[tuple[Build, list[Package], GBPMetadata | None]]]:
    events: list[tuple[Build, list[Package], GBPMetadata | None]] = []

    def postpull(
        *, build: Build, packages: list[Package], gbp_metadata: GBPMetadata | None
    ) -> None:
        events.append((build, packages, gbp_metadata))

    dispatcher.bind(postpull=postpull)

    yield events


def publish_events(
    _options: FixtureOptions, _fixtures: Fixtures
) -> FixtureContext[list[Build]]:
    events: list[Build] = []

    def publish(build: Build) -> None:
        events.append(build)

    dispatcher.bind(published=publish)

    yield events


@requires("publisher", prepull_events, postpull_events, publish_events)
class DispatcherTestCase(TestCase):
    maxDiff = None

    def test_pull_single(self) -> None:
        new_build = BuildFactory()
        publisher.pull(new_build)

        packages = publisher.storage.get_packages(new_build)
        expected = (
            publisher.record(new_build),
            packages,
            publisher.gbp_metadata(publisher.jenkins.get_metadata(new_build), packages),
        )
        self.assertEqual(self.fixtures.postpull_events, [expected])
        self.assertEqual(self.fixtures.prepull_events, [new_build])

    def test_pull_multi(self) -> None:
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
        self.assertEqual(self.fixtures.prepull_events, [build1, build2])
        self.assertEqual(self.fixtures.postpull_events, [event1, event2])

    def test_publish(self) -> None:
        new_build = BuildFactory()
        publisher.publish(new_build)

        record = publisher.record(new_build)
        self.assertEqual(self.fixtures.publish_events, [record])


@requires("publisher")
class MachineInfoTestCase(TestCase):
    """Tests for the MachineInfo thingie"""

    def test(self) -> None:
        # Given the "foo" builds, one of which is published
        first_build = BuildFactory(machine="foo")
        publisher.publish(first_build)
        latest_build = BuildFactory(machine="foo")
        publisher.pull(latest_build)

        # Given the "other" builds
        for build in BuildFactory.create_batch(3, machine="other"):
            publisher.pull(build)

        # When we get MachineInfo for foo
        machine_info = publisher.MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.machine, "foo")
        self.assertEqual(machine_info.build_count, 2)
        self.assertEqual(machine_info.latest_build, publisher.record(latest_build))
        self.assertEqual(machine_info.published_build, first_build)

    def test_empty_db(self) -> None:
        # When we get MachineInfo for foo
        machine_info = publisher.MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.machine, "foo")
        self.assertEqual(machine_info.build_count, 0)
        self.assertEqual(machine_info.latest_build, None)
        self.assertEqual(machine_info.published_build, None)

    def test_builds_property(self) -> None:
        # Given the "foo" builds
        builds = BuildFactory.create_batch(3, machine="foo")
        for build in builds:
            publisher.pull(build)

        # Given the MachineInfo for foo
        machine_info = publisher.MachineInfo("foo")

        # When we call its .builds method
        result = machine_info.builds

        # Then we get the list of builds in reverse chronological order
        self.assertEqual(result, [publisher.record(i) for i in reversed(builds)])

    def test_tags_property_shows_tags_across_machines_builds(self) -> None:
        builds = BuildFactory.create_batch(3, machine="foo")
        for build in builds:
            publisher.pull(build)

        publisher.tag(builds[-1], "testing")
        publisher.tag(builds[0], "stable")

        machine_info = publisher.MachineInfo("foo")

        self.assertEqual(machine_info.tags, ["stable", "testing"])


def builds_fixture(_options: FixtureOptions, _fixtures: Fixtures) -> list[Build]:
    # So for this case let's say we have 4 builds.  None have built timestamps.  The
    # 3rd one is published (but has no built timestamp) and the first 2 are pulled
    # but not published:
    builds: list[Build] = BuildFactory.create_batch(4)
    return builds


@depends("publisher", builds_fixture)
def machine_info_fixture(
    _options: FixtureOptions, fixtures: Fixtures
) -> publisher.MachineInfo:
    machine = fixtures.builds[0].machine

    for build in fixtures.builds:
        MachineInfoLegacyBuiltTestCase.pull_build_with_no_built_timestamp(build)

    publisher.publish(fixtures.builds[2])

    assert not any(
        build.built for build in publisher.repo.build_records.for_machine(machine)
    )

    return publisher.MachineInfo(fixtures.builds[0].machine)


@requires(builds_fixture, "publisher", machine_info_fixture)
class MachineInfoLegacyBuiltTestCase(TestCase):
    """Test case for MachineInfo where built field is not always populated"""

    @staticmethod
    def pull_build_with_no_built_timestamp(build: Build) -> None:
        publisher.pull(build)
        publisher.repo.build_records.save(publisher.record(build), built=None)

    def test_build_count(self) -> None:
        self.assertEqual(self.fixtures.machine_info.build_count, 4)

    def test_builds(self) -> None:
        builds = self.fixtures.machine_info.builds

        expected = list(reversed([publisher.record(i) for i in self.fixtures.builds]))
        self.assertEqual(expected, builds)

    def test_latest_build(self) -> None:
        build4 = self.fixtures.builds[3]
        latest_build = self.fixtures.machine_info.latest_build

        self.assertEqual(publisher.record(build4), latest_build)

    def test_latest_with_latest_having_built_timestamp(self) -> None:
        build5 = BuildFactory()
        publisher.pull(build5)

        latest_build = self.fixtures.machine_info.latest_build

        self.assertEqual(publisher.record(build5), latest_build)

    def test_published_build(self) -> None:
        build3 = self.fixtures.builds[2]
        published_build = self.fixtures.machine_info.published_build

        self.assertEqual(build3, published_build)
        self.assertTrue(publisher.published(build3))


@requires("publisher")
class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self) -> None:
        response = publisher.schedule_build("babette")

        self.assertEqual("https://jenkins.invalid/job/babette/build", response)
        self.assertEqual(publisher.jenkins.scheduled_builds, ["babette"])
