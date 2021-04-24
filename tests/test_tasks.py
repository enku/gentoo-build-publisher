"""Unit tests for the tasks module"""
from datetime import datetime
from unittest import mock

from django.test import TestCase
from django.utils.timezone import make_aware

from gentoo_build_publisher import Storage
from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.tasks import publish_build, purge_build

from . import MockJenkins, TempHomeMixin
from .factories import BuildModelFactory


class BaseTestCase(TempHomeMixin, TestCase):
    """Base TestCase to mock jenkins and tempfile storage"""
    def setUp(self):
        super().setUp()

        # Mock storage for all tests
        patch = mock.patch("gentoo_build_publisher.models.Storage.from_settings")
        self.addCleanup(patch.stop)
        mock_storage = patch.start()
        self.storage = mock_storage.return_value = Storage(self.tmpdir)

        # Mock jenkins for all tests
        patch = mock.patch("gentoo_build_publisher.models.Jenkins.from_settings")
        self.addCleanup(patch.stop)
        mock_jenkins = patch.start()
        self.jenkins = mock_jenkins.return_value = MockJenkins(
            "http://jenkins.invalid/", "user", "key"
        )


class PublishBuildTestCase(BaseTestCase):
    """Unit tests for tasks.publish_build"""

    def test_publishes_build(self):
        """Should actually publish the build"""
        build_model = BuildModelFactory.create()

        with mock.patch("gentoo_build_publisher.tasks.purge_build"):
            publish_build(build_model.id)

        self.assertIs(self.storage.published(build_model.build), True)

    def test_calls_purge_build(self):
        """Should issue the purge_build task"""
        build_model = BuildModelFactory.create()

        with mock.patch("gentoo_build_publisher.tasks.purge_build") as mock_purge_build:
            publish_build(build_model.id)

        mock_purge_build.delay.assert_called_with(build_model.name)


class PurgeBuildTestCase(BaseTestCase):
    """Tests for the purge_build task"""
    def test_deletes_old_build(self):
        """Should remove purgable builds"""
        build_model = BuildModelFactory.create(
            number=1, submitted=make_aware(datetime(1970, 1, 1))
        )
        BuildModelFactory.create(number=2, submitted=make_aware(datetime(1970, 12, 31)))

        purge_build(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), False)

    def test_doesnt_delete_old_published_build(self):
        """Should not delete old build if published"""
        build_model = BuildModelFactory.create(
            number=1, submitted=make_aware(datetime(1970, 1, 1))
        )
        BuildModelFactory.create(number=2, submitted=make_aware(datetime(1970, 12, 31)))

        self.storage.publish(build_model.build, self.jenkins)
        purge_build(build_model.name)

        query = BuildModel.objects.filter(id=build_model.id)

        self.assertIs(query.exists(), True)
