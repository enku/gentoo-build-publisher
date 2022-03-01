"""Tests for the GBP publisher"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
from unittest import mock

from gentoo_build_publisher.jenkins import Jenkins
from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.publisher import (
    MachineInfo,
    SystemPublisher,
    build_publisher,
)
from gentoo_build_publisher.types import Content

from . import MockJenkins, TestCase
from .factories import BuildFactory

utc = datetime.timezone.utc


class BuildPublisherTestCase(TestCase):
    def test_publish(self):
        """.publish should publish the build artifact"""
        build = BuildFactory()

        build_publisher.publish(build)

        self.assertIs(build_publisher.storage.published(build), True)

    def test_pull_without_db(self):
        """pull creates db record and pulls from jenkins"""
        build = BuildFactory()

        build_publisher.pull(build)

        self.assertIs(build_publisher.storage.pulled(build), True)
        self.assertIs(build_publisher.records.exists(build), True)

    def test_pull_stores_build_logs(self):
        """Should store the logs of the build"""
        build = BuildFactory()

        build_publisher.pull(build)

        url = str(build_publisher.jenkins.logs_url(build))
        build_publisher.jenkins.get_build_logs_mock_get.assert_called_once()
        call_args = build_publisher.jenkins.get_build_logs_mock_get.call_args
        self.assertEqual(call_args[0][0], url)

        record = build_publisher.record(build)
        self.assertEqual(record.logs, "foo\n")

    def test_pull_updates_build_models_completed_field(self):
        """Should update the completed field with the current timestamp"""
        now = datetime.datetime.now()
        build = BuildFactory()

        with mock.patch("gentoo_build_publisher.publisher.utcnow") as mock_now:
            mock_now.return_value = now
            build_publisher.pull(build)

        record = build_publisher.record(build)
        self.assertEqual(record.completed, now.replace(tzinfo=utc))

    def test_pull_updates_build_models_built_field(self):
        build = BuildFactory()
        build_publisher.pull(build)

        record = build_publisher.record(build)

        jenkins_timestamp = datetime.datetime.utcfromtimestamp(
            self.artifact_builder.build_info(build).build_time / 1000
        ).replace(tzinfo=utc)
        self.assertEqual(record.built, jenkins_timestamp)

    def test_pull_does_not_download_when_already_pulled(self):
        build = BuildFactory()

        build_publisher.pull(build)

        with mock.patch.object(build_publisher.jenkins, "download_artifact") as mock_dl:
            build_publisher.pull(build)

        self.assertFalse(mock_dl.called)

    def test_purge_deletes_old_build(self):
        """Should remove purgable builds"""

        old_build = BuildFactory()
        build_publisher.pull(old_build)
        record = build_publisher.record(old_build)
        build_publisher.records.save(
            record, submitted=datetime.datetime(1970, 1, 1, tzinfo=utc)
        )

        new_build = BuildFactory()
        build_publisher.pull(new_build)
        record = build_publisher.record(new_build)
        build_publisher.records.save(
            record, submitted=datetime.datetime(1970, 12, 31, tzinfo=utc)
        )

        build_publisher.purge(old_build.machine)

        self.assertIs(build_publisher.records.exists(old_build), False)

        for item in Content:
            path = build_publisher.storage.get_path(old_build, item)
            self.assertIs(path.exists(), False, path)

    def test_purge_does_not_delete_old_kept_build(self):
        """Should remove purgable builds"""

        build = BuildFactory()
        build_publisher.records.save(
            build_publisher.record(build),
            submitted=datetime.datetime(1970, 1, 1, tzinfo=utc),
            keep=True,
        )
        build_publisher.records.save(
            build_publisher.record(BuildFactory()),
            submitted=datetime.datetime(1970, 12, 31, tzinfo=utc),
        )

        build_publisher.purge(build.machine)

        self.assertIs(build_publisher.records.exists(build), True)

    def test_purge_doesnt_delete_old_published_build(self):
        """Should not delete old build if published"""
        build = BuildFactory()

        build_publisher.publish(build)
        build_publisher.records.save(
            build_publisher.record(build),
            submitted=datetime.datetime(1970, 1, 1, tzinfo=utc),
        )
        build_publisher.records.save(
            build_publisher.record(BuildFactory()),
            submitted=datetime.datetime(1970, 12, 31, tzinfo=utc),
        )

        build_publisher.purge(build.machine)

        self.assertIs(build_publisher.records.exists(build), True)

    def test_update_build_metadata(self):
        # pylint: disable=protected-access
        build = BuildFactory()
        record = build_publisher.record(build)

        build_publisher._update_build_metadata(record)

        record = build_publisher.record(build)
        self.assertEqual(record.logs, "foo\n")
        self.assertIsNot(record.completed, None)

    def test_diff_binpkgs_should_be_empty_if_left_and_right_are_equal(self):
        left = BuildFactory()
        build_publisher.get_packages = mock.Mock(wraps=build_publisher.get_packages)
        right = left

        # This should actually fail if not short-circuited because the builds have not
        # been pulled
        diff = [*build_publisher.diff_binpkgs(left, right)]

        self.assertEqual(diff, [])
        self.assertEqual(build_publisher.get_packages.call_count, 0)


class MachineInfoTestCase(TestCase):
    """Tests for the MachineInfo thingie"""

    def test(self):
        # Given the "foo" builds, one of which is published
        first_build = BuildFactory(machine="foo")
        build_publisher.publish(first_build)
        latest_build = BuildFactory(machine="foo")
        build_publisher.pull(latest_build)

        # Given the "other" builds
        for build in BuildFactory.create_batch(3, machine="other"):
            build_publisher.pull(build)

        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.machine, "foo")
        self.assertEqual(machine_info.build_count, 2)
        self.assertEqual(
            machine_info.latest_build, build_publisher.record(latest_build)
        )
        self.assertEqual(machine_info.published_build, first_build)

    def test_empty_db(self):
        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.machine, "foo")
        self.assertEqual(machine_info.build_count, 0)
        self.assertEqual(machine_info.latest_build, None)
        self.assertEqual(machine_info.published_build, None)

    def test_builds_property(self):
        # Given the "foo" builds
        builds = BuildFactory.create_batch(3, machine="foo")
        for build in builds:
            build_publisher.pull(build)

        # Given the MachineInfo for foo
        machine_info = MachineInfo("foo")

        # When we call its .builds method
        result = machine_info.builds

        # Then we get the list of builds in reverse chronological order
        self.assertEqual(result, [build_publisher.record(i) for i in reversed(builds)])


class MachineInfoLegacyBuiltTestCase(TestCase):
    """Test case for MachineInfo where built field is not always populated"""

    def setUp(self):
        super().setUp()

        # So for this case let's say we have 4 builds.  None have built timestamps.  The
        # 3rd one is published (but has no built timestamp) and the first 2 are pulled
        # but not published:
        self.builds = BuildFactory.create_batch(4)
        machine = self.builds[0].machine

        build1 = self.builds[0]
        build_publisher.pull(build1)
        build_publisher.records.save(build_publisher.record(build1), built=None)

        build2 = self.builds[1]
        build_publisher.pull(build2)
        build_publisher.records.save(build_publisher.record(build2), built=None)

        build3 = self.builds[2]
        build_publisher.publish(build3)
        build_publisher.records.save(build_publisher.record(build3), built=None)

        build4 = self.builds[3]
        build_publisher.pull(build4)
        build_publisher.records.save(build_publisher.record(build4), built=None)

        assert (
            BuildModel.objects.filter(machine=machine, built__isnull=False).count() == 0
        )
        self.machine_info = MachineInfo(build1.machine)

    def test_build_count(self):
        self.assertEqual(self.machine_info.build_count, 4)

    def test_builds(self):
        builds = self.machine_info.builds

        expected = list(reversed([build_publisher.record(i) for i in self.builds]))
        self.assertEqual(expected, builds)

    def test_latest_build(self):
        build4 = self.builds[3]
        latest_build = self.machine_info.latest_build

        self.assertEqual(build_publisher.record(build4), latest_build)

    def test_latest_with_latest_having_built_timestamp(self):
        build5 = BuildFactory()
        build_publisher.pull(build5)

        latest_build = self.machine_info.latest_build

        self.assertEqual(build_publisher.record(build5), latest_build)

    def test_published_build(self):
        build3 = self.builds[2]
        published_build = self.machine_info.published_build

        self.assertEqual(build3, published_build)
        self.assertTrue(build_publisher.published(build3))


class SystemPublisherTestCase(TestCase):
    def test(self):
        publisher = SystemPublisher()

        self.assertIsInstance(publisher.jenkins, Jenkins)
        self.assertNotIsInstance(publisher.jenkins, MockJenkins)


class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self):
        with mock.patch.object(
            build_publisher.jenkins, "schedule_build"
        ) as mock_schedule_build:
            mock_queue_url = "https://jenkins.invalid/queue/item/31528/"
            mock_schedule_build.return_value = mock_queue_url
            response = build_publisher.schedule_build("babette")

        self.assertEqual(response, mock_queue_url)
        mock_schedule_build.assert_called_once_with("babette")
