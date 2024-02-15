"""Tests for the GBP publisher"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from yarl import URL

from gentoo_build_publisher import publisher
from gentoo_build_publisher.common import Build, Content, GBPMetadata, Package
from gentoo_build_publisher.records.memory import RecordDB
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.signals import dispatcher
from gentoo_build_publisher.utils.time import utctime

from . import BUILD_LOGS, TestCase, set_up_tmpdir_for_test
from .factories import BuildFactory, BuildRecordFactory


class BuildPublisherFromSettingsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.tmpdir = set_up_tmpdir_for_test(self)

    def test_from_settings_returns_publisher_with_given_settings(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="https://testserver.invalid/",
            RECORDS_BACKEND="memory",
            STORAGE_PATH=self.tmpdir / "test_from_settings",
        )
        pub = publisher.BuildPublisher.from_settings(settings)

        self.assertEqual(
            pub.jenkins.config.base_url, URL("https://testserver.invalid/")
        )
        self.assertEqual(pub.storage.root, self.tmpdir / "test_from_settings")
        self.assertIsInstance(pub.records, RecordDB)


class BuildPublisherTestCase(TestCase):  # pylint: disable=too-many-public-methods
    def setUp(self) -> None:
        super().setUp()

        self.build = BuildFactory()
        self.publisher = publisher._inst  # pylint: disable=protected-access

    def test_publish(self) -> None:
        """.publish should publish the build artifact"""
        self.publisher.publish(self.build)

        self.assertIs(self.publisher.storage.published(self.build), True)

    def test_pull_without_db(self) -> None:
        """pull creates db record and pulls from jenkins"""
        self.publisher.pull(self.build)

        self.assertIs(self.publisher.storage.pulled(self.build), True)
        self.assertIs(self.publisher.records.exists(self.build), True)

    def test_pull_stores_build_logs(self) -> None:
        """Should store the logs of the build"""
        self.publisher.pull(self.build)

        url = str(self.publisher.jenkins.url.logs(self.build))
        self.publisher.jenkins.get_build_logs_mock_get.assert_called_once_with(url)

        record = self.publisher.record(self.build)
        self.assertEqual(record.logs, BUILD_LOGS)

    def test_pull_updates_build_models_completed_field(self) -> None:
        """Should update the completed field with the current timestamp"""
        now = utctime()

        with mock.patch("gentoo_build_publisher.publisher.utctime") as mock_now:
            mock_now.return_value = now
            self.publisher.pull(self.build)

        record = self.publisher.record(self.build)
        self.assertEqual(record.completed, now)

    def test_pull_updates_build_models_built_field(self) -> None:
        self.publisher.pull(self.build)

        record = self.publisher.record(self.build)

        jenkins_timestamp = dt.datetime.utcfromtimestamp(
            self.artifact_builder.build_info(self.build).build_time / 1000
        ).replace(tzinfo=dt.UTC)
        self.assertEqual(record.built, jenkins_timestamp)

    def test_pull_does_not_download_when_already_pulled(self) -> None:
        self.publisher.pull(self.build)
        assert self.publisher.pulled(self.build)

        pulled = self.publisher.pull(self.build)

        self.assertFalse(pulled)

    def test_pulled_when_storage_is_ok_but_db_is_not(self) -> None:
        # On rare occasion (server crash) the build appears to be extracted but the
        # record.completed field is None.  In this case Publisher.pulled(build) should
        # be False
        with mock.patch.object(
            self.publisher, "_update_build_metadata"
        ) as update_build_metadata:
            # _update_build_metadata sets the completed attribute
            update_build_metadata.return_value = None, None, None  # dummy values
            self.publisher.pull(self.build)

        self.assertFalse(self.publisher.pulled(self.build))

    def test_build_timestamps(self) -> None:
        localtimezone = "gentoo_build_publisher.utils.time.LOCAL_TIMEZONE"
        with mock.patch(localtimezone, new=ZoneInfo("America/New_York")):
            submitted = dt.datetime(2024, 1, 19, 11, 5, 49, tzinfo=dt.UTC)
            now = "gentoo_build_publisher.utils.time.now"
            with mock.patch(now, return_value=submitted):
                self.artifact_builder.timer = 1705662194  # 2024-01-19 11:03 UTC
                build = BuildFactory()
                self.publisher.pull(build)
                record = self.publisher.record(build)

        ct = ZoneInfo("America/Chicago")
        self.assertEqual(record.built, dt.datetime(2024, 1, 19, 5, 3, 24, tzinfo=ct))
        self.assertEqual(
            record.submitted, dt.datetime(2024, 1, 19, 5, 5, 49, tzinfo=ct)
        )
        self.assertEqual(
            record.completed, dt.datetime(2024, 1, 19, 5, 5, 49, tzinfo=ct)
        )

    def test_pull_with_note(self) -> None:
        self.publisher.pull(self.build, note="This is a test")

        self.assertIs(self.publisher.storage.pulled(self.build), True)
        build_record = self.publisher.record(self.build)
        self.assertEqual(build_record.note, "This is a test")

    def test_pull_with_tags(self) -> None:
        tags = {"this", "is", "a", "test"}

        self.publisher.pull(self.build, tags=tags)

        self.assertIs(self.publisher.storage.pulled(self.build), True)
        self.assertEqual(set(self.publisher.tags(self.build)), tags)

    def test_purge_deletes_old_build(self) -> None:
        """Should remove purgeable builds"""
        old_build = self.build
        self.publisher.pull(old_build)
        record = self.publisher.record(old_build)
        self.publisher.records.save(
            record, submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
        )

        new_build = BuildFactory()
        self.publisher.pull(new_build)
        record = self.publisher.record(new_build)
        self.publisher.records.save(
            record, submitted=dt.datetime(1970, 12, 31, tzinfo=dt.UTC)
        )

        self.publisher.purge(old_build.machine)

        self.assertIs(self.publisher.records.exists(old_build), False)

        for item in Content:
            path = self.publisher.storage.get_path(old_build, item)
            self.assertIs(path.exists(), False, path)

    def test_purge_does_not_delete_old_tagged_builds(self) -> None:
        """Should remove purgeable builds"""

        kept_build = BuildFactory(machine="lighthouse")
        self.publisher.records.save(
            self.publisher.record(kept_build),
            submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC),
            keep=True,
        )
        tagged_build = BuildFactory(machine="lighthouse")
        self.publisher.records.save(
            self.publisher.record(tagged_build),
            submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC),
        )
        self.publisher.pull(tagged_build)
        self.publisher.tag(tagged_build, "prod")
        self.publisher.records.save(
            self.publisher.record(BuildFactory(machine="lighthouse")),
            submitted=dt.datetime(1970, 12, 31, tzinfo=dt.UTC),
        )

        self.publisher.purge("lighthouse")

        self.assertIs(self.publisher.records.exists(kept_build), True)
        self.assertIs(self.publisher.records.exists(tagged_build), True)

    def test_purge_doesnt_delete_old_published_build(self) -> None:
        """Should not delete old build if published"""
        self.publisher.publish(self.build)
        self.publisher.records.save(
            self.publisher.record(self.build),
            submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC),
        )
        self.publisher.records.save(
            self.publisher.record(BuildFactory()),
            submitted=dt.datetime(1970, 12, 31, tzinfo=dt.UTC),
        )

        self.publisher.purge(self.build.machine)

        self.assertIs(self.publisher.records.exists(self.build), True)

    def test_update_build_metadata(self) -> None:
        # pylint: disable=protected-access
        record = self.publisher.record(self.build)

        self.publisher._update_build_metadata(record)

        record = self.publisher.record(self.build)
        self.assertEqual(record.logs, BUILD_LOGS)
        self.assertIsNot(record.completed, None)

    def test_diff_binpkgs_should_be_empty_if_left_and_right_are_equal(self) -> None:
        left = self.build
        self.publisher.get_packages = mock.Mock(wraps=self.publisher.get_packages)
        right = left

        # This should actually fail if not short-circuited because the builds have not
        # been pulled
        diff = [*publisher.diff_binpkgs(left, right)]

        self.assertEqual(diff, [])
        self.assertEqual(self.publisher.get_packages.call_count, 0)

    def test_tags_returns_the_list_of_tags_except_empty_tag(self) -> None:
        self.publisher.publish(self.build)
        self.publisher.storage.tag(self.build, "prod")

        self.assertEqual(self.publisher.storage.get_tags(self.build), ["", "prod"])
        self.assertEqual(self.publisher.tags(self.build), ["prod"])

    def test_tag_tags_the_build_at_the_storage_layer(self) -> None:
        self.publisher.pull(self.build)
        self.publisher.tag(self.build, "prod")
        self.publisher.tag(self.build, "albert")

        self.assertEqual(publisher.storage.get_tags(self.build), ["albert", "prod"])

    def test_untag_removes_tag_from_the_build(self) -> None:
        self.publisher.pull(self.build)
        self.publisher.tag(self.build, "prod")
        self.publisher.tag(self.build, "albert")

        self.publisher.untag(self.build.machine, "albert")

        self.assertEqual(self.publisher.storage.get_tags(self.build), ["prod"])

    def test_untag_with_empty_unpublishes_the_build(self) -> None:
        self.publisher.publish(self.build)
        self.assertTrue(self.publisher.published(self.build))

        self.publisher.untag(self.build.machine, "")

        self.assertFalse(self.publisher.published(self.build))

    def test_save(self) -> None:
        r1 = BuildRecordFactory()
        r2 = publisher.save(r1, note="This is a test")

        self.assertEqual(r2.note, "This is a test")

        r3 = publisher.record(Build(r1.machine, r1.build_id))
        self.assertEqual(r2, r3)


class DispatcherTestCase(TestCase):
    maxDiff = None

    def setUp(self) -> None:
        super().setUp()

        self.publish_events: list[Build] = []
        dispatcher.bind(published=self.publish_handler)
        self.addCleanup(lambda: dispatcher.unbind(self.publish_handler))

        self.prepull_events: list[Build] = []
        self.postpull_events: list[tuple[Build, list[Package], GBPMetadata | None]] = []
        dispatcher.bind(prepull=self.prepull_handler)
        dispatcher.bind(postpull=self.postpull_handler)
        self.addCleanup(lambda: dispatcher.unbind(self.prepull_handler))
        self.addCleanup(lambda: dispatcher.unbind(self.postpull_handler))

    def publish_handler(self, *, build: Build) -> None:
        self.publish_events.append(build)

    def prepull_handler(self, *, build: Build) -> None:
        self.prepull_events.append(build)

    def postpull_handler(
        self, *, build: Build, packages: list[Package], gbp_metadata: GBPMetadata | None
    ) -> None:
        self.postpull_events.append((build, packages, gbp_metadata))

    def test_pull_single(self) -> None:
        new_build = BuildFactory()
        publisher.pull(new_build)

        packages = publisher.storage.get_packages(new_build)
        expected = (
            publisher.record(new_build),
            packages,
            publisher.gbp_metadata(publisher.jenkins.get_metadata(new_build), packages),
        )
        self.assertEqual(self.postpull_events, [expected])
        self.assertEqual(self.prepull_events, [new_build])

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
        self.assertEqual(self.prepull_events, [build1, build2])
        self.assertEqual(self.postpull_events, [event1, event2])

    def test_publish(self) -> None:
        new_build = BuildFactory()
        publisher.publish(new_build)

        record = publisher.record(new_build)
        self.assertEqual(self.publish_events, [record])


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


class MachineInfoLegacyBuiltTestCase(TestCase):
    """Test case for MachineInfo where built field is not always populated"""

    def setUp(self) -> None:
        super().setUp()

        # So for this case let's say we have 4 builds.  None have built timestamps.  The
        # 3rd one is published (but has no built timestamp) and the first 2 are pulled
        # but not published:
        self.builds = BuildFactory.create_batch(4)
        machine = self.builds[0].machine

        for build in self.builds:
            self.pull_build_with_no_built_timestamp(build)

        publisher.publish(self.builds[2])

        assert not any(build.built for build in publisher.records.for_machine(machine))
        self.machine_info = publisher.MachineInfo(self.builds[0].machine)

    def pull_build_with_no_built_timestamp(self, build: Build) -> None:
        publisher.pull(build)
        publisher.records.save(publisher.record(build), built=None)

    def test_build_count(self) -> None:
        self.assertEqual(self.machine_info.build_count, 4)

    def test_builds(self) -> None:
        builds = self.machine_info.builds

        expected = list(reversed([publisher.record(i) for i in self.builds]))
        self.assertEqual(expected, builds)

    def test_latest_build(self) -> None:
        build4 = self.builds[3]
        latest_build = self.machine_info.latest_build

        self.assertEqual(publisher.record(build4), latest_build)

    def test_latest_with_latest_having_built_timestamp(self) -> None:
        build5 = BuildFactory()
        publisher.pull(build5)

        latest_build = self.machine_info.latest_build

        self.assertEqual(publisher.record(build5), latest_build)

    def test_published_build(self) -> None:
        build3 = self.builds[2]
        published_build = self.machine_info.published_build

        self.assertEqual(build3, published_build)
        self.assertTrue(publisher.published(build3))


class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self) -> None:
        response = publisher.schedule_build("babette")

        self.assertEqual("https://jenkins.invalid/job/babette/build", response)
        self.assertEqual(publisher.jenkins.scheduled_builds, ["babette"])
