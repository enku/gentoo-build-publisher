"""Tests for GBP managers"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
from unittest import mock

from gentoo_build_publisher.build import BuildID, Content
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import Build, MachineInfo
from gentoo_build_publisher.models import BuildModel, KeptBuild
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage

from . import TestCase
from .factories import BuildFactory, BuildModelFactory, MockJenkins

utc = datetime.timezone.utc


class BuildTestCase(TestCase):
    def test_instantiate_with_wrong_class(self):
        with self.assertRaises(TypeError) as context:
            Build(1)

        error = context.exception

        expected = ("build argument must be one of [BuildID, BuildRecord]. Got int.",)
        self.assertEqual(error.args, expected)

    def test_publish(self):
        """.publish should publish the build artifact"""
        build = BuildFactory.build()

        build.publish()

        self.assertIs(build.storage.published(build.id), True)

    def test_pull_without_db(self):
        """pull creates db instance and pulls from jenkins"""
        build_id = BuildID("babette.193")
        settings = Settings.from_environ()
        jenkins = MockJenkins.from_settings(settings)
        build = Build(build_id, jenkins=jenkins)

        build.pull()

        self.assertIs(build.storage.pulled(build.id), True)
        self.assertIsNot(build.record, None)

    def test_pull_stores_build_logs(self):
        """Should store the logs of the build"""
        build = BuildFactory.build()

        build.pull()

        url = str(build.logs_url())
        build.jenkins.get_build_logs_mock_get.assert_called_once()
        call_args = build.jenkins.get_build_logs_mock_get.call_args
        self.assertEqual(call_args[0][0], url)

        self.assertEqual(build.record.logs, "foo\n")

    def test_pull_updates_build_models_completed_field(self):
        """Should update the completed field with the current timestamp"""
        now = datetime.datetime.now()
        build = BuildFactory.build()

        with mock.patch("gentoo_build_publisher.managers.utcnow") as mock_now:
            mock_now.return_value = now
            build.pull()

        build = Build(build.id)
        self.assertEqual(build.record.completed, now.replace(tzinfo=utc))

    def test_purge_deletes_old_build(self):
        """Should remove purgable builds"""
        build_model = BuildModelFactory.create(
            number=1, submitted=datetime.datetime(1970, 1, 1, tzinfo=utc)
        )
        BuildModelFactory.create(
            number=2, submitted=datetime.datetime(1970, 12, 31, tzinfo=utc)
        )

        build_id = BuildID(f"{build_model.name}.{build_model.number}")
        settings = Settings.from_environ()
        jenkins = MockJenkins.from_settings(settings)
        storage = Storage(self.tmpdir)
        storage.extract_artifact(build_id, jenkins.download_artifact(build_id))

        Build.purge(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), False)

        for item in Content:
            path = storage.get_path(build_id, item)
            self.assertIs(path.exists(), False, path)

    def test_purge_does_not_delete_old_kept_build(self):
        """Should remove purgable builds"""
        build_model = BuildModelFactory.create(
            number=1, submitted=datetime.datetime(1970, 1, 1, tzinfo=utc)
        )
        KeptBuild.objects.create(build_model=build_model)
        BuildModelFactory.create(
            number=2, submitted=datetime.datetime(1970, 12, 31, tzinfo=utc)
        )

        Build.purge(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), True)

    def test_purge_doesnt_delete_old_published_build(self):
        """Should not delete old build if published"""
        build = BuildFactory.create(
            build=BuildModelFactory.create(
                number=1, submitted=datetime.datetime(1970, 1, 1, tzinfo=utc)
            )
        )
        BuildModelFactory.create(
            number=2, submitted=datetime.datetime(1970, 12, 31, tzinfo=utc)
        )

        build.publish()
        Build.purge(build.id.name)

        query = BuildModel.objects.filter(name=build.id.name, number=build.id.number)

        self.assertIs(query.exists(), True)

    def test_purge_doesnt_delete_build_when_keptbuild_exists(self):
        """Should not delete build when KeptBuild exists for the BuildModel"""
        build_model = BuildModelFactory.create(
            number=1, submitted=datetime.datetime(1970, 1, 1, tzinfo=utc)
        )
        KeptBuild.objects.create(build_model=build_model)
        BuildModelFactory.create(
            number=2, submitted=datetime.datetime(1970, 12, 31, tzinfo=utc)
        )

        Build.purge(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), True)

    def test_update_build_metadata(self):
        build = BuildFactory.create()
        settings = Settings.from_environ()
        MockJenkins.from_settings(settings)

        build.update_build_metadata()
        self.assertEqual(build.record.logs, "foo\n")
        self.assertIsNot(build.record.completed, None)

    def test_diff_binpkgs_should_be_empty_if_left_and_right_are_equal(self):
        left = BuildFactory.create()
        left.get_packages = mock.Mock(wraps=left.get_packages)
        right = left

        # This should actually fail if not short-circuited because the builds have not
        # been pulled
        diff = [*Build.diff_binpkgs(left, right)]

        self.assertEqual(diff, [])
        self.assertEqual(left.get_packages.call_count, 0)


class MachineInfoTestCase(TestCase):
    """Tests for the MachineInfo thingie"""

    def test(self):
        # Given the "foo" builds, one of which is published
        first_build = BuildFactory.create(build_attr__build_id__name="foo")
        first_build.publish()
        latest_build = BuildFactory.create(build_attr__build_id__name="foo")

        # Given the "other" builds
        BuildFactory.create_batch(3)

        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.name, "foo")
        self.assertEqual(machine_info.build_count, 2)
        self.assertEqual(machine_info.latest_build, latest_build)
        self.assertEqual(machine_info.published, first_build)

    def test_empty_db(self):
        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.name, "foo")
        self.assertEqual(machine_info.build_count, 0)
        self.assertEqual(machine_info.latest_build, None)
        self.assertEqual(machine_info.published, None)

    def test_builds_method(self):
        # Given the "foo" builds
        first_build = BuildFactory.create(
            build_attr=BuildDB.model_to_record(BuildModelFactory.create(name="foo"))
        )
        second_build = BuildFactory.create(
            build_attr=BuildDB.model_to_record(BuildModelFactory.create(name="foo"))
        )
        third_build = BuildFactory.create(
            build_attr=BuildDB.model_to_record(BuildModelFactory.create(name="foo"))
        )

        # Given the MachineInfo for foo
        machine_info = MachineInfo("foo")

        # When we call its .builds method
        builds = machine_info.builds()

        # Then we get the list of builds in reverse chronological order
        self.assertEqual(builds, [third_build, second_build, first_build])


class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self):
        name = "babette"
        settings = Settings.from_environ()
        mock_path = "gentoo_build_publisher.managers.Jenkins.from_settings"

        with mock.patch(mock_path) as mock_jenkins:
            mock_jenkins.return_value.schedule_build.return_value = (
                "https://jenkins.invalid/queue/item/31528/"
            )
            response = Build.schedule_build(name)

        self.assertEqual(response, "https://jenkins.invalid/queue/item/31528/")
        mock_jenkins.assert_called_once_with(settings)
        mock_jenkins.return_value.schedule_build.assert_called_once_with(name)
