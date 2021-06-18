"""Unit tests for the tasks module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=no-value-for-parameter,no-self-use
import os
from datetime import datetime
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from requests import HTTPError

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.diff import Change, Status
from gentoo_build_publisher.models import BuildModel, KeptBuild
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import StorageBuild
from gentoo_build_publisher.tasks import publish_build, pull_build, purge_build

from . import MockJenkinsBuild, TempHomeMixin
from .factories import BuildManFactory, BuildModelFactory


class PublishBuildTestCase(TempHomeMixin, TestCase):
    """Unit tests for tasks.publish_build"""

    @mock.patch("gentoo_build_publisher.tasks.BuildMan")
    def test_publishes_build(self, buildmanager_mock):
        """Should actually publish the build"""
        build = Build(name="babette", number=193)
        buildman = BuildManFactory(build=build)
        buildmanager_mock.return_value = buildman

        with mock.patch("gentoo_build_publisher.tasks.purge_build"):
            publish_build("babette", 193)

        self.assertIs(buildman.published(), True)
        buildmanager_mock.assert_called_with(build)


class PurgeBuildTestCase(TempHomeMixin, TestCase):
    """Tests for the purge_build task"""

    def test_deletes_old_build(self):
        """Should remove purgable builds"""
        build_model = BuildModelFactory.create(
            number=1, submitted=timezone.make_aware(datetime(1970, 1, 1))
        )
        BuildModelFactory.create(
            number=2, submitted=timezone.make_aware(datetime(1970, 12, 31))
        )

        build = Build(name=build_model.name, number=build_model.number)
        settings = Settings.from_environ()
        jenkins_build = MockJenkinsBuild.from_settings(build, settings)
        storage_build = StorageBuild(build, self.tmpdir)
        storage_build.extract_artifact(jenkins_build.download_artifact())

        purge_build(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), False)

        for item in Build.Content:
            path = storage_build.get_path(item)
            self.assertIs(path.exists(), False, path)

    def test_does_not_delete_old_kept_build(self):
        """Should remove purgable builds"""
        build_model = BuildModelFactory.create(
            number=1, submitted=timezone.make_aware(datetime(1970, 1, 1))
        )
        KeptBuild.objects.create(build_model=build_model)
        BuildModelFactory.create(
            number=2, submitted=timezone.make_aware(datetime(1970, 12, 31))
        )

        purge_build(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), True)

    def test_doesnt_delete_old_published_build(self):
        """Should not delete old build if published"""
        buildman = BuildManFactory.build(
            build=BuildModelFactory.create(
                number=1, submitted=timezone.make_aware(datetime(1970, 1, 1))
            )
        )
        BuildModelFactory.create(
            number=2, submitted=timezone.make_aware(datetime(1970, 12, 31))
        )

        buildman.publish()
        purge_build(buildman.name)

        query = BuildModel.objects.filter(id=buildman.id)

        self.assertIs(query.exists(), True)

    def test_doesnt_delete_build_when_keptbuild_exists(self):
        """Should not delete build when KeptBuild exists for the BuildModel"""
        build_model = BuildModelFactory.create(
            number=1, submitted=timezone.make_aware(datetime(1970, 1, 1))
        )
        KeptBuild.objects.create(build_model=build_model)
        BuildModelFactory.create(
            number=2, submitted=timezone.make_aware(datetime(1970, 12, 31))
        )

        purge_build(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), True)


@mock.patch("gentoo_build_publisher.tasks.BuildMan")
class PullBuildTestCase(TempHomeMixin, TestCase):
    """Tests for the pull_build task"""

    def test_pulls_build(self, buildmanager_mock):
        """Should actually pull the build"""
        buildman = BuildManFactory.build()
        buildmanager_mock.return_value = buildman

        with mock.patch("gentoo_build_publisher.tasks.purge_build"):
            pull_build(buildman.name, buildman.number)

        self.assertIs(buildman.pulled(), True)

    def test_stores_build_logs(self, buildmanager_mock):
        """Should store the logs of the build"""
        buildman = BuildManFactory.build()
        buildmanager_mock.return_value = buildman

        with mock.patch("gentoo_build_publisher.tasks.purge_build"):
            pull_build(buildman.name, buildman.number)

        url = str(buildman.logs_url())
        buildman.jenkins_build.get_build_logs_mock_get.assert_called_once()
        call_args = buildman.jenkins_build.get_build_logs_mock_get.call_args
        self.assertEqual(call_args[0][0], url)

        self.assertEqual(buildman.db.logs, "foo\n")

    def test_writes_built_pkgs_in_note(self, buildmanager_mock):
        prev_build = BuildManFactory.build()
        prev_build.db.model.completed = timezone.now()
        prev_build.db.model.save()

        buildman = BuildManFactory.build()
        buildmanager_mock.return_value = buildman

        with mock.patch("gentoo_build_publisher.tasks.purge_build"):
            with mock.patch("gentoo_build_publisher.diff.dirdiff") as mock_dirdiff:
                mock_dirdiff.return_value = iter(
                    [
                        Change(item="app-crypt/gpgme-1.14.0-1", status=Status.REMOVED),
                        Change(item="app-crypt/gpgme-1.14.0-2", status=Status.ADDED),
                        Change(item="sys-apps/sandbox-2.24-1", status=Status.CHANGED),
                        Change(item="sys-apps/sandbox-2.24-1", status=Status.CHANGED),
                    ]
                )
                pull_build(buildman.name, buildman.number)

        buildman.db.refresh()

        self.assertEqual(
            buildman.db.note,
            "Packages built:\n\n* app-crypt/gpgme-1.14.0-2\n* sys-apps/sandbox-2.24-1",
        )

    def test_calls_purge_build(self, buildmanager_mock):
        """Should issue the purge_build task when setting is true"""
        buildman = BuildManFactory.build()
        buildmanager_mock.return_value = buildman

        with mock.patch("gentoo_build_publisher.tasks.purge_build") as mock_purge_build:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "1"}):
                pull_build(buildman.name, buildman.number)

        mock_purge_build.delay.assert_called_with(buildman.name)

    def test_does_not_call_purge_build(self, buildmanager_mock):
        """Should not issue the purge_build task when setting is false"""
        buildman = BuildManFactory.build()
        buildmanager_mock.return_value = buildman

        with mock.patch("gentoo_build_publisher.tasks.purge_build") as mock_purge_build:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "0"}):
                pull_build(buildman.name, buildman.number)

        mock_purge_build.delay.assert_not_called()

    def test_updates_build_models_completed_field(self, buildmanager_mock):
        """Should update the completed field with the current timestamp"""
        now = timezone.now()
        buildman = BuildManFactory.build()
        buildmanager_mock.return_value = buildman

        with mock.patch("gentoo_build_publisher.tasks.purge_build"):
            with mock.patch("gentoo_build_publisher.tasks.timezone.now") as mock_now:
                mock_now.return_value = now
                pull_build(buildman.name, buildman.number)

        buildman.db.model.refresh_from_db()
        self.assertEqual(buildman.db.model.completed, now)

    def test_should_delete_db_model_when_download_fails(self, buildmanager_mock):
        buildman = BuildManFactory.build()
        buildmanager_mock.return_value = buildman

        with mock.patch.object(
            buildman.jenkins_build, "download_artifact"
        ) as download_artifact_mock:
            download_artifact_mock.side_effect = HTTPError
            pull_build(buildman.name, buildman.number)

        with self.assertRaises(BuildModel.DoesNotExist):
            buildman.db.model.refresh_from_db()
