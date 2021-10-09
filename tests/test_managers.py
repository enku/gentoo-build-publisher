"""Tests for GBP managers"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
from unittest import mock

from gentoo_build_publisher.build import Build, Content
from gentoo_build_publisher.managers import BuildMan, MachineInfo, schedule_build
from gentoo_build_publisher.models import BuildModel, KeptBuild
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import StorageBuild

from . import TestCase, package_entry
from .factories import BuildManFactory, BuildModelFactory, MockJenkinsBuild

utc = datetime.timezone.utc


class BuildManTestCase(TestCase):
    def test_instantiate_with_wrong_class(self):
        with self.assertRaises(TypeError) as context:
            BuildMan(1)

        error = context.exception

        expected = ("build argument must be one of [Build, BuildDB]. Got int.",)
        self.assertEqual(error.args, expected)

    def test_publish(self):
        """.publish should publish the build artifact"""
        buildman = BuildManFactory.build()

        buildman.publish()

        self.assertIs(buildman.storage_build.published(), True)

    def test_pull_without_db(self):
        """pull creates db instance and pulls from jenkins"""
        build = Build(name="babette", number=193)
        settings = Settings.from_environ()
        jenkins_build = MockJenkinsBuild.from_settings(build, settings)
        buildman = BuildMan(build, jenkins_build=jenkins_build)

        buildman.pull()

        self.assertIs(buildman.storage_build.pulled(), True)
        self.assertIsNot(buildman.db, None)

    def test_pull_stores_build_logs(self):
        """Should store the logs of the build"""
        buildman = BuildManFactory.build()

        buildman.pull()

        url = str(buildman.logs_url())
        buildman.jenkins_build.get_build_logs_mock_get.assert_called_once()
        call_args = buildman.jenkins_build.get_build_logs_mock_get.call_args
        self.assertEqual(call_args[0][0], url)

        self.assertEqual(buildman.db.logs, "foo\n")

    def test_pull_updates_build_models_completed_field(self):
        """Should update the completed field with the current timestamp"""
        now = datetime.datetime.now()
        buildman = BuildManFactory.build()

        with mock.patch("gentoo_build_publisher.managers.utcnow") as mock_now:
            mock_now.return_value = now
            buildman.pull()

        buildman.db.model.refresh_from_db()
        self.assertEqual(buildman.db.model.completed, now.replace(tzinfo=utc))

    def test_pull_writes_built_pkgs_in_note(self):
        now = datetime.datetime.now().replace(tzinfo=utc)
        prev_build = BuildManFactory.build()
        prev_build.db.model.completed = now
        prev_build.db.model.save()
        prev_build.get_path(Content.BINPKGS).mkdir(parents=True)
        (prev_build.get_path(Content.BINPKGS) / "Packages").write_text("")

        buildman = BuildManFactory.build()
        buildman.pull()
        buildman.db.refresh()

        self.assertEqual(
            buildman.db.note,
            "Packages built:\n"
            "\n"
            "* acct-group/sgx-0-1\n"
            "* app-admin/perl-cleaner-2.30-1\n"
            "* app-arch/unzip-6.0_p26-1\n"
            "* app-crypt/gpgme-1.14.0-1",
        )

    def test_purge_deletes_old_build(self):
        """Should remove purgable builds"""
        build_model = BuildModelFactory.create(
            number=1, submitted=datetime.datetime(1970, 1, 1, tzinfo=utc)
        )
        BuildModelFactory.create(
            number=2, submitted=datetime.datetime(1970, 12, 31, tzinfo=utc)
        )

        build = Build(name=build_model.name, number=build_model.number)
        settings = Settings.from_environ()
        jenkins_build = MockJenkinsBuild.from_settings(build, settings)
        storage_build = StorageBuild(build, self.tmpdir)
        storage_build.extract_artifact(jenkins_build.download_artifact())

        BuildMan.purge(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), False)

        for item in Content:
            path = storage_build.get_path(item)
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

        BuildMan.purge(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), True)

    def test_purge_doesnt_delete_old_published_build(self):
        """Should not delete old build if published"""
        buildman = BuildManFactory.build(
            build=BuildModelFactory.create(
                number=1, submitted=datetime.datetime(1970, 1, 1, tzinfo=utc)
            )
        )
        BuildModelFactory.create(
            number=2, submitted=datetime.datetime(1970, 12, 31, tzinfo=utc)
        )

        buildman.publish()
        BuildMan.purge(buildman.name)

        query = BuildModel.objects.filter(id=buildman.id)

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

        BuildMan.purge(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), True)

    def test_update_build_metadata_when_no_previous_build(self):
        buildman = BuildManFactory.create()
        settings = Settings.from_environ()
        MockJenkinsBuild.from_settings(buildman.build, settings)

        buildman.update_build_metadata()
        self.assertEqual(buildman.db.logs, "foo\n")
        self.assertIsNot(buildman.db.completed, None)

    def test_update_build_metadata_with_previous_build(self):
        previous_buildman = BuildManFactory.create()
        previous_buildman.pull()
        package_index = (
            previous_buildman.storage_build.get_path(Content.BINPKGS) / "Packages"
        )
        package_index.write_text(package_entry("sys-fs/btrfs-progs-5.13"))

        buildman = BuildManFactory.create()
        buildman.storage_build.extract_artifact(
            buildman.jenkins_build.download_artifact()
        )
        # Artificially update a package
        package_index = buildman.storage_build.get_path(Content.BINPKGS) / "Packages"
        package_index.write_text(package_entry("sys-fs/btrfs-progs-5.14"))

        buildman.update_build_metadata(previous_buildman.db)
        self.assertEqual(
            buildman.db.note, "Packages built:\n\n* sys-fs/btrfs-progs-5.14-1"
        )


class MachineInfoTestCase(TestCase):
    """Tests for the MachineInfo thingie"""

    def test(self):
        # Given the "foo" builds, one of which is published
        first_build = BuildManFactory.create(build_attr__build_model__name="foo")
        first_build.publish()
        latest_build = BuildManFactory.create(build_attr__build_model__name="foo")

        # Given the "other" builds
        BuildManFactory.create_batch(3, build_attr__build_model__name="bar")

        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.name, "foo")
        self.assertEqual(machine_info.build_count, 2)
        self.assertEqual(machine_info.latest_build.number, latest_build.number)
        self.assertEqual(machine_info.published.number, first_build.number)

    def test_empty_db(self):
        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.name, "foo")
        self.assertEqual(machine_info.build_count, 0)
        self.assertEqual(machine_info.latest_build, None)
        self.assertEqual(machine_info.published, None)


class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self):
        name = "babette"
        settings = Settings.from_environ()
        mock_path = "gentoo_build_publisher.managers.schedule_jenkins_build"

        with mock.patch(mock_path) as mock_jenkins_build:
            mock_jenkins_build.return_value = (
                "https://jenkins.invalid/queue/item/31528/"
            )
            response = schedule_build(name)

        self.assertEqual(response, "https://jenkins.invalid/queue/item/31528/")
        mock_jenkins_build.assert_called_once_with(name, settings)
