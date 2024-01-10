"""Tests for the GBP publisher"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
import os
import unittest
from unittest import mock

from yarl import URL

from gentoo_build_publisher.common import Build, Content, GBPMetadata, Package
from gentoo_build_publisher.publisher import BuildPublisher, MachineInfo
from gentoo_build_publisher.records.memory import RecordDB
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.signals import dispatcher
from gentoo_build_publisher.utils.time import utctime

from . import BUILD_LOGS, TestCase, set_up_tmpdir_for_test
from .factories import BuildFactory

utc = datetime.timezone.utc


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
        publisher = BuildPublisher.from_settings(settings)

        self.assertEqual(
            publisher.jenkins.config.base_url, URL("https://testserver.invalid/")
        )
        self.assertEqual(publisher.storage.root, self.tmpdir / "test_from_settings")
        self.assertIsInstance(publisher.records, RecordDB)


class BuildPublisherTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.build = BuildFactory()

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

        jenkins_timestamp = datetime.datetime.utcfromtimestamp(
            self.artifact_builder.build_info(self.build).build_time / 1000
        ).replace(tzinfo=utc)
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
        with mock.patch.object(self.publisher, "_update_build_metadata"):
            # _update_build_metadata sets the completed attribute
            self.publisher.pull(self.build)

        self.assertFalse(self.publisher.pulled(self.build))

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
            record, submitted=datetime.datetime(1970, 1, 1, tzinfo=utc)
        )

        new_build = BuildFactory()
        self.publisher.pull(new_build)
        record = self.publisher.record(new_build)
        self.publisher.records.save(
            record, submitted=datetime.datetime(1970, 12, 31, tzinfo=utc)
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
            submitted=datetime.datetime(1970, 1, 1, tzinfo=utc),
            keep=True,
        )
        tagged_build = BuildFactory(machine="lighthouse")
        self.publisher.records.save(
            self.publisher.record(tagged_build),
            submitted=datetime.datetime(1970, 1, 1, tzinfo=utc),
        )
        self.publisher.pull(tagged_build)
        self.publisher.tag(tagged_build, "prod")
        self.publisher.records.save(
            self.publisher.record(BuildFactory(machine="lighthouse")),
            submitted=datetime.datetime(1970, 12, 31, tzinfo=utc),
        )

        self.publisher.purge("lighthouse")

        self.assertIs(self.publisher.records.exists(kept_build), True)
        self.assertIs(self.publisher.records.exists(tagged_build), True)

    def test_purge_doesnt_delete_old_published_build(self) -> None:
        """Should not delete old build if published"""
        self.publisher.publish(self.build)
        self.publisher.records.save(
            self.publisher.record(self.build),
            submitted=datetime.datetime(1970, 1, 1, tzinfo=utc),
        )
        self.publisher.records.save(
            self.publisher.record(BuildFactory()),
            submitted=datetime.datetime(1970, 12, 31, tzinfo=utc),
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
        diff = [*self.publisher.diff_binpkgs(left, right)]

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

        self.assertEqual(
            self.publisher.storage.get_tags(self.build), ["albert", "prod"]
        )

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
        self.publisher.pull(new_build)

        packages = self.publisher.storage.get_packages(new_build)
        expected = (
            self.publisher.record(new_build),
            packages,
            self.publisher.gbp_metadata(
                self.publisher.jenkins.get_metadata(new_build), packages
            ),
        )
        self.assertEqual(self.postpull_events, [expected])
        self.assertEqual(self.prepull_events, [new_build])

    def test_pull_multi(self) -> None:
        build1 = BuildFactory()
        build2 = BuildFactory(machine="fileserver")
        self.publisher.pull(build1)
        self.publisher.pull(build2)

        record1 = self.publisher.record(build1)
        record2 = self.publisher.record(build2)

        packages = self.publisher.storage.get_packages(record1)
        event1 = (
            record1,
            packages,
            self.publisher.gbp_metadata(
                self.publisher.jenkins.get_metadata(record1), packages
            ),
        )
        packages = self.publisher.storage.get_packages(record2)
        event2 = (
            record2,
            packages,
            self.publisher.gbp_metadata(
                self.publisher.jenkins.get_metadata(record2), packages
            ),
        )
        self.assertEqual(self.prepull_events, [build1, build2])
        self.assertEqual(self.postpull_events, [event1, event2])

    def test_publish(self) -> None:
        new_build = BuildFactory()
        self.publisher.publish(new_build)

        record = self.publisher.record(new_build)
        self.assertEqual(self.publish_events, [record])


class MachineInfoTestCase(TestCase):
    """Tests for the MachineInfo thingie"""

    def test(self) -> None:
        # Given the "foo" builds, one of which is published
        first_build = BuildFactory(machine="foo")
        self.publisher.publish(first_build)
        latest_build = BuildFactory(machine="foo")
        self.publisher.pull(latest_build)

        # Given the "other" builds
        for build in BuildFactory.create_batch(3, machine="other"):
            self.publisher.pull(build)

        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.machine, "foo")
        self.assertEqual(machine_info.build_count, 2)
        self.assertEqual(machine_info.latest_build, self.publisher.record(latest_build))
        self.assertEqual(machine_info.published_build, first_build)

    def test_empty_db(self) -> None:
        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.machine, "foo")
        self.assertEqual(machine_info.build_count, 0)
        self.assertEqual(machine_info.latest_build, None)
        self.assertEqual(machine_info.published_build, None)

    def test_builds_property(self) -> None:
        # Given the "foo" builds
        builds = BuildFactory.create_batch(3, machine="foo")
        for build in builds:
            self.publisher.pull(build)

        # Given the MachineInfo for foo
        machine_info = MachineInfo("foo")

        # When we call its .builds method
        result = machine_info.builds

        # Then we get the list of builds in reverse chronological order
        self.assertEqual(result, [self.publisher.record(i) for i in reversed(builds)])

    def test_tags_property_shows_tags_across_machines_builds(self) -> None:
        builds = BuildFactory.create_batch(3, machine="foo")
        for build in builds:
            self.publisher.pull(build)

        self.publisher.tag(builds[-1], "testing")
        self.publisher.tag(builds[0], "stable")

        machine_info = MachineInfo("foo")

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

        self.publisher.publish(self.builds[2])

        assert not any(
            build.built for build in self.publisher.records.for_machine(machine)
        )
        self.machine_info = MachineInfo(self.builds[0].machine)

    def pull_build_with_no_built_timestamp(self, build: Build) -> None:
        self.publisher.pull(build)
        self.publisher.records.save(self.publisher.record(build), built=None)

    def test_build_count(self) -> None:
        self.assertEqual(self.machine_info.build_count, 4)

    def test_builds(self) -> None:
        builds = self.machine_info.builds

        expected = list(reversed([self.publisher.record(i) for i in self.builds]))
        self.assertEqual(expected, builds)

    def test_latest_build(self) -> None:
        build4 = self.builds[3]
        latest_build = self.machine_info.latest_build

        self.assertEqual(self.publisher.record(build4), latest_build)

    def test_latest_with_latest_having_built_timestamp(self) -> None:
        build5 = BuildFactory()
        self.publisher.pull(build5)

        latest_build = self.machine_info.latest_build

        self.assertEqual(self.publisher.record(build5), latest_build)

    def test_published_build(self) -> None:
        build3 = self.builds[2]
        published_build = self.machine_info.published_build

        self.assertEqual(build3, published_build)
        self.assertTrue(self.publisher.published(build3))


class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self) -> None:
        response = self.publisher.schedule_build("babette")

        self.assertEqual("https://jenkins.invalid/job/babette/build", response)
        self.assertEqual(self.publisher.jenkins.scheduled_builds, ["babette"])


class GetPublisherTestCase(unittest.TestCase):
    """Tests for the get_publisher function"""

    def setUp(self) -> None:
        super().setUp()

        BuildPublisher.get_publisher.cache_clear()
        self.tmpdir = set_up_tmpdir_for_test(self)

    def test_creates_publisher_from_env_variables_when_global_is_none(self) -> None:
        env = {
            "BUILD_PUBLISHER_JENKINS_BASE_URL": "https://testserver.invalid/",
            "BUILD_PUBLISHER_RECORDS_BACKEND": "memory",
            "BUILD_PUBLISHER_STORAGE_PATH": str(self.tmpdir / "test_get_publisher"),
        }
        with mock.patch.dict(os.environ, env, clear=True):
            publisher = BuildPublisher.get_publisher()

        self.assertEqual(
            publisher.jenkins.config.base_url, URL("https://testserver.invalid/")
        )
        self.assertEqual(publisher.storage.root, self.tmpdir / "test_get_publisher")
        self.assertIsInstance(publisher.records, RecordDB)
