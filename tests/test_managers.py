"""Tests for GBP managers"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
from unittest import mock

from gentoo_build_publisher.build import Content
from gentoo_build_publisher.managers import MachineInfo

from . import TestCase
from .factories import BuildIDFactory, BuildPublisherFactory

utc = datetime.timezone.utc


class BuildPublisherTestCase(TestCase):
    def test_publish(self):
        """.publish should publish the build artifact"""
        build_id = BuildIDFactory()
        build_publisher = BuildPublisherFactory()

        build_publisher.publish(build_id)

        self.assertIs(build_publisher.storage.published(build_id), True)

    def test_pull_without_db(self):
        """pull creates db record and pulls from jenkins"""
        build_publisher = BuildPublisherFactory()
        build_id = BuildIDFactory()

        build_publisher.pull(build_id)

        self.assertIs(build_publisher.storage.pulled(build_id), True)
        self.assertIs(build_publisher.records.exists(build_id), True)

    def test_pull_stores_build_logs(self):
        """Should store the logs of the build"""
        build_publisher = BuildPublisherFactory()
        build_id = BuildIDFactory()

        build_publisher.pull(build_id)

        url = str(build_publisher.jenkins.logs_url(build_id))
        build_publisher.jenkins.get_build_logs_mock_get.assert_called_once()
        call_args = build_publisher.jenkins.get_build_logs_mock_get.call_args
        self.assertEqual(call_args[0][0], url)

        record = build_publisher.record(build_id)
        self.assertEqual(record.logs, "foo\n")

    def test_pull_updates_build_models_completed_field(self):
        """Should update the completed field with the current timestamp"""
        now = datetime.datetime.now()
        build_publisher = BuildPublisherFactory()
        build_id = BuildIDFactory()

        with mock.patch("gentoo_build_publisher.managers.utcnow") as mock_now:
            mock_now.return_value = now
            build_publisher.pull(build_id)

        record = build_publisher.record(build_id)
        self.assertEqual(record.completed, now.replace(tzinfo=utc))

    def test_pull_does_not_download_when_already_pulled(self):
        build_id = BuildIDFactory()
        build_publisher = BuildPublisherFactory()

        build_publisher.pull(build_id)

        with mock.patch.object(build_publisher.jenkins, "download_artifact") as mock_dl:
            build_publisher.pull(build_id)

        self.assertFalse(mock_dl.called)

    def test_purge_deletes_old_build(self):
        """Should remove purgable builds"""
        build_publisher = BuildPublisherFactory()

        old_build = BuildIDFactory()
        build_publisher.pull(old_build)
        record = build_publisher.record(old_build)
        build_publisher.records.save(
            record, submitted=datetime.datetime(1970, 1, 1, tzinfo=utc)
        )

        new_build = BuildIDFactory()
        build_publisher.pull(new_build)
        record = build_publisher.record(new_build)
        build_publisher.records.save(
            record, submitted=datetime.datetime(1970, 12, 31, tzinfo=utc)
        )

        build_publisher.purge(old_build.name)

        self.assertIs(build_publisher.records.exists(old_build), False)

        for item in Content:
            path = build_publisher.storage.get_path(old_build, item)
            self.assertIs(path.exists(), False, path)

    def test_purge_does_not_delete_old_kept_build(self):
        """Should remove purgable builds"""
        build_publisher = BuildPublisherFactory()

        build_id = BuildIDFactory()
        build_publisher.records.save(
            build_publisher.record(build_id),
            submitted=datetime.datetime(1970, 1, 1, tzinfo=utc),
            keep=True,
        )
        build_publisher.records.save(
            build_publisher.record(BuildIDFactory()),
            submitted=datetime.datetime(1970, 12, 31, tzinfo=utc),
        )

        build_publisher.purge(build_id.name)

        self.assertIs(build_publisher.records.exists(build_id), True)

    def test_purge_doesnt_delete_old_published_build(self):
        """Should not delete old build if published"""
        build_publisher = BuildPublisherFactory()
        build_id = BuildIDFactory()

        build_publisher.publish(build_id)
        build_publisher.records.save(
            build_publisher.record(build_id),
            submitted=datetime.datetime(1970, 1, 1, tzinfo=utc),
        )
        build_publisher.records.save(
            build_publisher.record(BuildIDFactory()),
            submitted=datetime.datetime(1970, 12, 31, tzinfo=utc),
        )

        build_publisher.purge(build_id.name)

        self.assertIs(build_publisher.records.exists(build_id), True)

    def test_update_build_metadata(self):
        # pylint: disable=protected-access
        build_publisher = BuildPublisherFactory()
        build_id = BuildIDFactory()
        record = build_publisher.record(build_id)

        build_publisher._update_build_metadata(record)

        record = build_publisher.record(build_id)
        self.assertEqual(record.logs, "foo\n")
        self.assertIsNot(record.completed, None)

    def test_diff_binpkgs_should_be_empty_if_left_and_right_are_equal(self):
        build_publisher = BuildPublisherFactory()
        left = BuildIDFactory()
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
        build_publisher = BuildPublisherFactory()

        # Given the "foo" builds, one of which is published
        first_build = BuildIDFactory(name="foo")
        build_publisher.publish(first_build)
        latest_build = BuildIDFactory(name="foo")
        build_publisher.pull(latest_build)

        # Given the "other" builds
        for build_id in BuildIDFactory.create_batch(3, name="other"):
            build_publisher.pull(build_id)

        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.name, "foo")
        self.assertEqual(machine_info.build_count, 2)
        self.assertEqual(machine_info.latest_build, latest_build)
        self.assertEqual(machine_info.published_build, first_build)

    def test_empty_db(self):
        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.name, "foo")
        self.assertEqual(machine_info.build_count, 0)
        self.assertEqual(machine_info.latest_build, None)
        self.assertEqual(machine_info.published_build, None)

    def test_builds_property(self):
        build_publisher = BuildPublisherFactory()

        # Given the "foo" builds
        builds = BuildIDFactory.create_batch(3, name="foo")
        for build_id in builds:
            build_publisher.pull(build_id)

        # Given the MachineInfo for foo
        machine_info = MachineInfo("foo")

        # When we call its .builds method
        result = machine_info.builds

        # Then we get the list of builds in reverse chronological order
        self.assertEqual(result, [*reversed(builds)])


class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self):
        build_publisher = BuildPublisherFactory()

        with mock.patch.object(
            build_publisher.jenkins, "schedule_build"
        ) as mock_schedule_build:
            mock_queue_url = "https://jenkins.invalid/queue/item/31528/"
            mock_schedule_build.return_value = mock_queue_url
            response = build_publisher.schedule_build("babette")

        self.assertEqual(response, mock_queue_url)
        mock_schedule_build.assert_called_once_with("babette")
