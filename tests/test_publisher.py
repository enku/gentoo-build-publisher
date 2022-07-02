"""Tests for the GBP publisher"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
from unittest import mock

from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.publisher import MachineInfo
from gentoo_build_publisher.types import Content

from . import TestCase
from .factories import BuildFactory

utc = datetime.timezone.utc


class BuildPublisherTestCase(TestCase):
    def test_publish(self):
        """.publish should publish the build artifact"""
        build = BuildFactory()

        self.publisher.publish(build)

        self.assertIs(self.publisher.storage.published(build), True)

    def test_pull_without_db(self):
        """pull creates db record and pulls from jenkins"""
        build = BuildFactory()

        self.publisher.pull(build)

        self.assertIs(self.publisher.storage.pulled(build), True)
        self.assertIs(self.publisher.records.exists(build), True)

    def test_pull_stores_build_logs(self):
        """Should store the logs of the build"""
        build = BuildFactory()

        self.publisher.pull(build)

        url = str(self.publisher.jenkins.logs_url(build))
        self.publisher.jenkins.get_build_logs_mock_get.assert_called_once()
        call_args = self.publisher.jenkins.get_build_logs_mock_get.call_args
        self.assertEqual(call_args[0][0], url)

        record = self.publisher.record(build)
        self.assertEqual(record.logs, "foo\n")

    def test_pull_updates_build_models_completed_field(self):
        """Should update the completed field with the current timestamp"""
        now = datetime.datetime.now()
        build = BuildFactory()

        with mock.patch("gentoo_build_publisher.publisher.utcnow") as mock_now:
            mock_now.return_value = now
            self.publisher.pull(build)

        record = self.publisher.record(build)
        self.assertEqual(record.completed, now.replace(tzinfo=utc))

    def test_pull_updates_build_models_built_field(self):
        build = BuildFactory()
        self.publisher.pull(build)

        record = self.publisher.record(build)

        jenkins_timestamp = datetime.datetime.utcfromtimestamp(
            self.artifact_builder.build_info(build).build_time / 1000
        ).replace(tzinfo=utc)
        self.assertEqual(record.built, jenkins_timestamp)

    def test_pull_does_not_download_when_already_pulled(self):
        build = BuildFactory()

        self.publisher.pull(build)
        assert self.publisher.pulled(build)

        pulled = self.publisher.pull(build)

        self.assertFalse(pulled)

    def test_purge_deletes_old_build(self):
        """Should remove purgable builds"""

        old_build = BuildFactory()
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

    def test_purge_does_not_delete_old_kept_build(self):
        """Should remove purgable builds"""

        build = BuildFactory()
        self.publisher.records.save(
            self.publisher.record(build),
            submitted=datetime.datetime(1970, 1, 1, tzinfo=utc),
            keep=True,
        )
        self.publisher.records.save(
            self.publisher.record(BuildFactory()),
            submitted=datetime.datetime(1970, 12, 31, tzinfo=utc),
        )

        self.publisher.purge(build.machine)

        self.assertIs(self.publisher.records.exists(build), True)

    def test_purge_doesnt_delete_old_published_build(self):
        """Should not delete old build if published"""
        build = BuildFactory()

        self.publisher.publish(build)
        self.publisher.records.save(
            self.publisher.record(build),
            submitted=datetime.datetime(1970, 1, 1, tzinfo=utc),
        )
        self.publisher.records.save(
            self.publisher.record(BuildFactory()),
            submitted=datetime.datetime(1970, 12, 31, tzinfo=utc),
        )

        self.publisher.purge(build.machine)

        self.assertIs(self.publisher.records.exists(build), True)

    def test_update_build_metadata(self):
        # pylint: disable=protected-access
        build = BuildFactory()
        record = self.publisher.record(build)

        self.publisher._update_build_metadata(record)

        record = self.publisher.record(build)
        self.assertEqual(record.logs, "foo\n")
        self.assertIsNot(record.completed, None)

    def test_diff_binpkgs_should_be_empty_if_left_and_right_are_equal(self):
        left = BuildFactory()
        self.publisher.get_packages = mock.Mock(wraps=self.publisher.get_packages)
        right = left

        # This should actually fail if not short-circuited because the builds have not
        # been pulled
        diff = [*self.publisher.diff_binpkgs(left, right)]

        self.assertEqual(diff, [])
        self.assertEqual(self.publisher.get_packages.call_count, 0)


class DispatcherTestCase(TestCase):
    maxDiff = None

    def setUp(self):
        super().setUp()

        self.publisher.dispatcher.bind(pulled=self.pull_handler)
        self.pull_events = []

        self.addCleanup(lambda: self.publisher.dispatcher.unbind(self.pull_handler))

    def pull_handler(self, *, build, packages, gbp_metadata):
        self.pull_events.append([build, packages, gbp_metadata])

    def test_pull_single(self):
        new_build = BuildFactory()
        self.publisher.pull(new_build)

        packages = self.publisher.storage.get_packages(new_build)
        expected = [
            self.publisher.record(new_build),
            packages,
            self.publisher.gbp_metadata(
                self.publisher.jenkins.get_metadata(new_build), packages
            ),
        ]
        self.assertEqual(self.pull_events, [expected])

    def test_pull_multi(self):
        build1 = BuildFactory()
        build2 = BuildFactory(machine="fileserver")
        self.publisher.pull(build1)
        self.publisher.pull(build2)

        record1 = self.publisher.record(build1)
        record2 = self.publisher.record(build2)

        packages = self.publisher.storage.get_packages(record1)
        event1 = [
            record1,
            packages,
            self.publisher.gbp_metadata(
                self.publisher.jenkins.get_metadata(record1), packages
            ),
        ]
        packages = self.publisher.storage.get_packages(record2)
        event2 = [
            record2,
            packages,
            self.publisher.gbp_metadata(
                self.publisher.jenkins.get_metadata(record2), packages
            ),
        ]
        self.assertEqual(self.pull_events, [event1, event2])


class MachineInfoTestCase(TestCase):
    """Tests for the MachineInfo thingie"""

    def test(self):
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
            self.publisher.pull(build)

        # Given the MachineInfo for foo
        machine_info = MachineInfo("foo")

        # When we call its .builds method
        result = machine_info.builds

        # Then we get the list of builds in reverse chronological order
        self.assertEqual(result, [self.publisher.record(i) for i in reversed(builds)])


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
        self.publisher.pull(build1)
        self.publisher.records.save(self.publisher.record(build1), built=None)

        build2 = self.builds[1]
        self.publisher.pull(build2)
        self.publisher.records.save(self.publisher.record(build2), built=None)

        build3 = self.builds[2]
        self.publisher.publish(build3)
        self.publisher.records.save(self.publisher.record(build3), built=None)

        build4 = self.builds[3]
        self.publisher.pull(build4)
        self.publisher.records.save(self.publisher.record(build4), built=None)

        assert (
            BuildModel.objects.filter(machine=machine, built__isnull=False).count() == 0
        )
        self.machine_info = MachineInfo(build1.machine)

    def test_build_count(self):
        self.assertEqual(self.machine_info.build_count, 4)

    def test_builds(self):
        builds = self.machine_info.builds

        expected = list(reversed([self.publisher.record(i) for i in self.builds]))
        self.assertEqual(expected, builds)

    def test_latest_build(self):
        build4 = self.builds[3]
        latest_build = self.machine_info.latest_build

        self.assertEqual(self.publisher.record(build4), latest_build)

    def test_latest_with_latest_having_built_timestamp(self):
        build5 = BuildFactory()
        self.publisher.pull(build5)

        latest_build = self.machine_info.latest_build

        self.assertEqual(self.publisher.record(build5), latest_build)

    def test_published_build(self):
        build3 = self.builds[2]
        published_build = self.machine_info.published_build

        self.assertEqual(build3, published_build)
        self.assertTrue(self.publisher.published(build3))


class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self):
        response = self.publisher.schedule_build("babette")

        self.assertEqual("https://jenkins.invalid/job/babette/build", response)
        self.assertEqual(self.publisher.jenkins.scheduled_builds, ["babette"])
