"""Unit tests for gbp views"""
import os
from unittest import mock

from django.http.response import Http404
from django.test import RequestFactory, TestCase

from gentoo_build_publisher.models import Build
from gentoo_build_publisher.views import delete, publish

from . import mock_get_artifact, mock_home_dir
from .factories import BuildFactory


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
        build = BuildFactory.create()

        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = publish(request, build.build_name, build.build_number)

        self.assertEqual(response.status_code, 200)
        mock_pb.delay.assert_called_once_with(build.pk)


class DeleteViewTestCase(TestCase):
    """Tests for the delete view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

    @mock_home_dir
    def test_post_deletes_build(self):
        """Should delete the build when POSTed"""
        build = BuildFactory.create()

        # When we download the artifact
        with mock_get_artifact():
            build.publish()

        self.assertTrue(os.path.exists(build.binpkgs_dir))
        self.assertTrue(os.path.exists(build.repos_dir))

        request = self.request.post("/delete/")
        response = delete(request, build.build_name, build.build_number)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'{"deleted": true, "error": null}')

        query = Build.objects.filter(
            build_name=build.build_name, build_number=build.build_number
        )
        self.assertFalse(query.exists())
        self.assertFalse(os.path.exists(build.binpkgs_dir))
        self.assertFalse(os.path.exists(build.repos_dir))

    def test_build_does_not_exist(self):
        """Should return a 404 response when build does not exist"""
        request = self.request.post("/delete/")

        with self.assertRaises(Http404):
            delete(request, "babette", "3000")
