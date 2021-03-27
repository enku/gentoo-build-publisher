"""Unit tests for gbp views"""
import datetime
import os
import tempfile
from unittest import mock

from django.http.response import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from gentoo_build_publisher.conf import settings
from gentoo_build_publisher.models import Build
from gentoo_build_publisher.views import delete, publish

from . import test_data


class PublishViewTestCase(TestCase):
    """Tests for the publish view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

    def test_publish_new(self):
        """Should publish brand new builds"""
        request = self.request.post("/publish/")
        build_name = "babette"
        build_number = "193"

        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = publish(request, build_name, build_number)

        self.assertEqual(response.status_code, 200)
        build = Build.objects.get(build_name=build_name, build_number=build_number)
        mock_pb.delay.assert_called_once_with(build.pk)

    def test_publish_existing(self):
        """Should publish brand new builds"""
        request = self.request.post("/publish/")
        build_name = "babette"
        build_number = "193"
        build = Build.objects.create(
            build_name=build_name, build_number=build_number, submitted=timezone.now()
        )

        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = publish(request, build_name, build_number)

        self.assertEqual(response.status_code, 200)
        mock_pb.delay.assert_called_once_with(build.pk)


class DeleteViewTestCase(TestCase):
    """Tests for the delete view"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home_dir = self.temp_dir.name
        patch = mock.patch.object(settings, "HOME_DIR", self.home_dir)
        patch.start()
        self.addCleanup(patch.stop)

        submitted = datetime.datetime(2021, 3, 23, 18, 39).replace(
            tzinfo=datetime.timezone.utc
        )
        self.build = Build.objects.create(
            build_name="babette", build_number=193, submitted=submitted
        )
        self.request = RequestFactory()

    def test_post_deletes_build(self):
        """Should delete the build when POSTed"""
        build = self.build

        with mock.patch("gentoo_build_publisher.models.requests.get") as mock_get:
            response = mock_get.return_value
            response.iter_content.return_value = iter(
                [
                    test_data("build.tar.gz"),
                ]
            )
            # When we download the artifact
            build.publish()

        self.assertTrue(os.path.exists(build.binpkgs_dir))
        self.assertTrue(os.path.exists(build.repos_dir))

        request = self.request.post("/delete/")
        response = delete(request, "babette", "193")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'{"deleted": true, "error": null}')

        query = Build.objects.filter(build_name="babette", build_number=193)
        self.assertFalse(query.exists())
        self.assertFalse(os.path.exists(build.binpkgs_dir))
        self.assertFalse(os.path.exists(build.repos_dir))

    def test_build_does_not_exist(self):
        """Should return a 404 response when build does not exist"""
        request = self.request.post("/delete/")

        with self.assertRaises(Http404):
            response = delete(request, "babette", "3000")
