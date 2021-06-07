"""Unit tests for gbp views"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from django.test import TestCase

from gentoo_build_publisher import Settings
from gentoo_build_publisher.models import BuildLog, BuildModel

from . import MockJenkins, TempHomeMixin
from .factories import BuildModelFactory

BASE_DIR = Path(__file__).resolve().parent / "data"


class PublishViewTestCase(TempHomeMixin, TestCase):
    """Tests for the publish view"""

    def test_publish_new(self):
        """Should publish brand new builds"""
        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = self.client.post("/publish/babette/193/")

        self.assertEqual(response.status_code, 200)
        build_model = BuildModel.objects.get(name="babette", number=193)
        mock_pb.delay.assert_called_once_with(build_model.pk)

    def test_publish_existing(self):
        """Should publish existing builds"""
        build_model = BuildModelFactory.create()
        build = build_model.build

        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = self.client.post(f"/publish/{build.name}/{build.number}/")

        self.assertEqual(response.status_code, 200)
        mock_pb.delay.assert_called_once_with(build_model.pk)


class PullViewTestCase(TempHomeMixin, TestCase):
    """Tests for the pull view"""

    def test_publish_new(self):
        """Should publish brand new builds"""
        with mock.patch("gentoo_build_publisher.views.pull_build") as mock_pb:
            response = self.client.post("/pull/babette/193/")

        self.assertEqual(response.status_code, 200)
        build_model = BuildModel.objects.get(name="babette", number=193)
        mock_pb.delay.assert_called_once_with(build_model.pk)


class ListBuildsViewTestCase(TempHomeMixin, TestCase):
    """Tests for the list_builds view"""

    def setUp(self):
        super().setUp()

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
        response = self.client.get("/builds/bogus/")

        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            response.json(),
            {"error": "No completed builds exist with that name", "builds": []},
        )

    def test_should_return_the_list_of_completed_builds(self):
        response = self.client.get("/builds/babette/")

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["builds"]), 2)


class LatestViewTestCase(TempHomeMixin, TestCase):
    """Tests for the latest view"""

    def setUp(self):
        super().setUp()

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
        response = self.client.get("/latest/bogus/")

        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            json.loads(response.content),
            {"error": "No completed builds exist with that name"},
        )

    def test_should_return_the_latest_submitted_completed(self):
        response = self.client.get("/latest/babette/")

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

    def test_returns_logs_when_there_are_logs(self):
        build_model = BuildModelFactory.create()
        BuildLog.objects.create(build_model=build_model, logs="foo\n")

        response = self.client.get(f"/logs/{build_model.name}/{build_model.number}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertEqual(response.content, b"foo\n")

    def test_gives_404_response_when_there_are_no_logs(self):
        build_model = BuildModelFactory.create()

        response = self.client.get(f"/logs/{build_model.name}/{build_model.number}/")

        self.assertEqual(response.status_code, 404)


class DeleteViewTestCase(TempHomeMixin, TestCase):
    """Tests for the delete view"""

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

        response = self.client.post(f"/delete/{build.name}/{build.number}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True, "error": None})

        query = BuildModel.objects.filter(name=build.name, number=build.number)
        self.assertFalse(query.exists())

        for item in build.Content:
            self.assertFalse(storage.get_path(build, item).exists())

    def test_build_does_not_exist(self):
        """Should return a 404 response when build does not exist"""
        response = self.client.post("/delete/3000/")

        self.assertEqual(response.status_code, 404)


class DiffBuildsViewTestCase(TempHomeMixin, TestCase):
    """Tests for the diff_builds view"""

    def test(self):
        left_bm = BuildModelFactory.create(name="babette", number=132)
        right_bm = BuildModelFactory.create(name="babette", number=147)
        left_path = str(BASE_DIR / "binpkgs" / "babette.132")
        right_path = str(BASE_DIR / "binpkgs" / "babette.147")

        with mock.patch("gentoo_build_publisher.Storage.get_path") as mock_get_path:
            mock_get_path.side_effect = (left_path, right_path)

            response = self.client.get("/diff/babette/132/147/")

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["error"], None)
        self.assertEqual(
            data["diff"]["builds"], [left_bm.as_dict(), right_bm.as_dict()]
        )

        self.assertEqual(len(data["diff"]["items"]), 6)
