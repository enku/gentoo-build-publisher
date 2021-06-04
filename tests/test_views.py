"""Unit tests for gbp views"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import json
from datetime import datetime
from unittest import mock

from django.http.response import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from gentoo_build_publisher import Settings
from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.views import delete, latest, publish, pull

from . import MockJenkins, TempHomeMixin
from .factories import BuildModelFactory


class PublishViewTestCase(TempHomeMixin, TestCase):
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
        build_model = BuildModel.objects.get(name=build_name, number=build_number)
        mock_pb.delay.assert_called_once_with(build_model.pk)

    def test_publish_existing(self):
        """Should publish brand new builds"""
        request = self.request.post("/publish/")
        build_model = BuildModelFactory.create()
        build = build_model.build

        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = publish(request, build.name, build.number)

        self.assertEqual(response.status_code, 200)
        mock_pb.delay.assert_called_once_with(build_model.pk)


class PullViewTestCase(TempHomeMixin, TestCase):
    """Tests for the pull view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

    def test_publish_new(self):
        """Should publish brand new builds"""
        request = self.request.post("/pull/")
        build_name = "babette"
        build_number = "193"

        with mock.patch("gentoo_build_publisher.views.pull_build") as mock_pb:
            response = pull(request, build_name, build_number)

        self.assertEqual(response.status_code, 200)
        build_model = BuildModel.objects.get(name=build_name, number=build_number)
        mock_pb.delay.assert_called_once_with(build_model.pk)


class LatestViewTestCase(TempHomeMixin, TestCase):
    """Tests for the latest view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

        BuildModelFactory.create(
            submitted=timezone.make_aware(datetime(1970, 1, 1)),
            completed=timezone.make_aware(datetime(1970, 1, 4)),
        )
        self.latest = BuildModelFactory.create(
            submitted=timezone.make_aware(datetime(1970, 1, 2)),
            completed=timezone.make_aware(datetime(1970, 1, 2)),
        )
        BuildModelFactory.create(
            submitted=timezone.make_aware(datetime(1970, 1, 3)),
        )

    def test_when_no_builds_should_respond_with_404(self):
        request = self.request.get("/latest/bogus/")
        build_name = "bogus"

        response = latest(request, build_name)

        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            json.loads(response.content),
            {"error": "No completed builds exist with that name"},
        )

    def test_should_return_the_latest_submitted_completed(self):
        request = self.request.get("/latest/babette/")
        build_name = "babette"

        response = latest(request, build_name)

        self.assertEqual(response.status_code, 200)
        name = self.latest.name
        number = self.latest.number
        expected = {
            "error": None,
            "name": name,
            "number": number,
            "published": False,
            "url": f"https://jenkins.invalid/job/{name}/{number}/artifact/build.tar.gz",
        }

        self.assertEqual(json.loads(response.content), expected)


class DeleteViewTestCase(TempHomeMixin, TestCase):
    """Tests for the delete view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

    def test_post_deletes_build(self):
        """Should delete the build when POSTed"""
        build_model = BuildModelFactory.create()
        build = build_model.build
        storage = build_model.storage
        jenkins = MockJenkins.from_settings(
            Settings(
                STORAGE_PATH="/dev/null", JENKINS_BASE_URL="https://jenkins.invalid/"
            )
        )

        # When we download the artifact
        storage.publish(build, jenkins)

        self.assertTrue(storage.get_path(build, build.Content.BINPKGS).exists())
        self.assertTrue(storage.get_path(build, build.Content.REPOS).exists())

        request = self.request.post("/delete/")
        response = delete(request, build.name, build.number)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'{"deleted": true, "error": null}')

        query = BuildModel.objects.filter(name=build.name, number=build.number)
        self.assertFalse(query.exists())
        self.assertFalse(storage.get_path(build, build.Content.BINPKGS).exists())
        self.assertFalse(storage.get_path(build, build.Content.REPOS).exists())

    def test_build_does_not_exist(self):
        """Should return a 404 response when build does not exist"""
        request = self.request.post("/delete/")

        with self.assertRaises(Http404):
            delete(request, "babette", "3000")
