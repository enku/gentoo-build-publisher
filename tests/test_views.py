"""Unit tests for gbp views"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from django.http.response import Http404
from django.test import RequestFactory, TestCase

from gentoo_build_publisher import Settings
from gentoo_build_publisher.models import BuildLog, BuildModel
from gentoo_build_publisher.views import (
    delete,
    diff_builds,
    latest,
    list_builds,
    logs,
    publish,
    pull,
)

from . import MockJenkins, TempHomeMixin
from .factories import BuildModelFactory

BASE_DIR = Path(__file__).resolve().parent / "data"


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
            response = publish(
                request, build_name=build_name, build_number=build_number
            )

        self.assertEqual(response.status_code, 200)
        build_model = BuildModel.objects.get(name=build_name, number=build_number)
        mock_pb.delay.assert_called_once_with(build_model.pk)

    def test_publish_existing(self):
        """Should publish brand new builds"""
        request = self.request.post("/publish/")
        build_model = BuildModelFactory.create()
        build = build_model.build

        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = publish(
                request, build_name=build.name, build_number=build.number
            )

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
            response = pull(request, build_name=build_name, build_number=build_number)

        self.assertEqual(response.status_code, 200)
        build_model = BuildModel.objects.get(name=build_name, number=build_number)
        mock_pb.delay.assert_called_once_with(build_model.pk)


class ListBuildsViewTestCase(TempHomeMixin, TestCase):
    """Tests for the list_builds view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

        BuildModelFactory.create(
            submitted=datetime(1970, 1, 1).replace(tzinfo=timezone.utc),
            completed=datetime(1970, 1, 4).replace(tzinfo=timezone.utc),
        )
        self.latest = BuildModelFactory.create(
            submitted=datetime(1970, 1, 2).replace(tzinfo=timezone.utc),
            completed=datetime(1970, 1, 2).replace(tzinfo=timezone.utc),
        )
        BuildModelFactory.create(
            submitted=datetime(1970, 1, 3).replace(tzinfo=timezone.utc),
        )

    def test_when_no_builds_should_respond_with_404(self):
        request = self.request.get("/builds/bogus/")

        response = list_builds(request, build_name="bogus")

        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            json.loads(response.content),
            {"error": "No completed builds exist with that name", "builds": []},
        )

    def test_should_return_the_list_of_completed_builds(self):
        request = self.request.get("/builds/babette/")

        response = list_builds(request, build_name="babette")

        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(len(data["builds"]), 2)


class LatestViewTestCase(TempHomeMixin, TestCase):
    """Tests for the latest view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

        BuildModelFactory.create(
            submitted=datetime(1970, 1, 1).replace(tzinfo=timezone.utc),
            completed=datetime(1970, 1, 4).replace(tzinfo=timezone.utc),
        )
        self.latest = BuildModelFactory.create(
            submitted=datetime(1970, 1, 2).replace(tzinfo=timezone.utc),
            completed=datetime(1970, 1, 2).replace(tzinfo=timezone.utc),
        )
        BuildModelFactory.create(
            submitted=datetime(1970, 1, 3).replace(tzinfo=timezone.utc),
        )

    def test_when_no_builds_should_respond_with_404(self):
        request = self.request.get("/latest/bogus/")
        build_name = "bogus"

        response = latest(request, build_name=build_name)

        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            json.loads(response.content),
            {"error": "No completed builds exist with that name"},
        )

    def test_should_return_the_latest_submitted_completed(self):
        request = self.request.get("/latest/babette/")
        build_name = "babette"

        response = latest(request, build_name=build_name)

        self.assertEqual(response.status_code, 200)
        name = self.latest.name
        number = self.latest.number
        expected = {
            "error": None,
            "name": name,
            "note": None,
            "number": number,
            "published": False,
            "submitted": self.latest.submitted.isoformat(),
            "completed": self.latest.completed.isoformat(),
            "url": f"https://jenkins.invalid/job/{name}/{number}/artifact/build.tar.gz",
        }

        self.assertEqual(json.loads(response.content), expected)


class LogsViewTestCase(TempHomeMixin, TestCase):
    """Tests for the logs view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

    def test_returns_logs_when_there_are_logs(self):
        build_model = BuildModelFactory.create()
        BuildLog.objects.create(build_model=build_model, logs="foo\n")

        request = self.request.get("/logs/{build_model.name}/{build_model.number}/")
        response = logs(
            request, build_name=build_model.name, build_number=build_model.number
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertEqual(response.content, b"foo\n")

    def test_gives_404_response_when_there_are_no_logs(self):
        build_model = BuildModelFactory.create()

        request = self.request.get("/logs/{build_model.name}/{build_model.number}/")

        with self.assertRaises(Http404):
            logs(request, build_name=build_model.name, build_number=build_model.number)


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
        response = delete(request, build_name=build.name, build_number=build.number)

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


class DiffBuildsViewTestCase(TempHomeMixin, TestCase):
    """Tests for the diff_builds view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

    def test(self):
        build_name = "babette"
        left = 132
        right = 147

        left_bm = BuildModelFactory.create(name="babette", number=132)
        right_bm = BuildModelFactory.create(name="babette", number=147)
        left_path = str(BASE_DIR / "binpkgs" / "babette.132")
        right_path = str(BASE_DIR / "binpkgs" / "babette.147")

        with mock.patch("gentoo_build_publisher.Storage.get_path") as mock_get_path:
            mock_get_path.side_effect = (left_path, right_path)
            request = self.request.get("/diff/babette/132/147/")

            response = diff_builds(request, build_name, left, right)

        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["error"], None)
        self.assertEqual(
            data["diff"]["builds"], [left_bm.as_dict(), right_bm.as_dict()]
        )

        self.assertEqual(len(data["diff"]["items"]), 6)
