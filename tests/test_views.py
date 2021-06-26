"""Unit tests for gbp views"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from django.test import TestCase

from gentoo_build_publisher.build import Build, Content
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.models import BuildLog, BuildModel

from . import TempHomeMixin
from .factories import BuildManFactory, BuildModelFactory

BASE_DIR = Path(__file__).resolve().parent / "data"


class PublishViewTestCase(TempHomeMixin, TestCase):
    """Tests for the publish view"""

    def test_publish(self):
        """Should publish builds"""
        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = self.client.post("/publish/babette/193/")

        self.assertEqual(response.status_code, 200)
        mock_pb.delay.assert_called_once_with("babette", 193)

    def test_should_not_schedule_task_if_already_pulled(self):
        build = BuildManFactory.build()
        build.pull()

        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = self.client.post(f"/publish/{build.name}/{build.number}/")

        self.assertEqual(response.status_code, 200)
        mock_pb.delay.assert_not_called()
        self.assertTrue(build.published())


class PullViewTestCase(TempHomeMixin, TestCase):
    """Tests for the pull view"""

    def test_publish_new(self):
        """Should publish brand new builds"""
        with mock.patch("gentoo_build_publisher.views.pull_build") as mock_pb:
            response = self.client.post("/pull/babette/193/")

        self.assertEqual(response.status_code, 200)
        mock_pb.delay.assert_called_once_with("babette", 193)

        buildman = BuildMan(Build(name="babette", number=193))
        expected = buildman.as_dict()
        expected["error"] = None
        self.assertEqual(response.json(), expected)


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
            response.json(),
            {"error": "No completed builds exist with that name"},
        )

    def test_should_return_the_latest_submitted_completed(self):
        response = self.client.get("/latest/babette/")

        self.assertEqual(response.status_code, 200)

        expected = BuildMan(BuildDB(self.latest)).as_dict()
        expected["error"] = None

        self.assertEqual(response.json(), expected)


class ShowBuildViewTestCase(TempHomeMixin, TestCase):
    def test_returns_json_repr(self):
        build_model = BuildModelFactory.create()

        response = self.client.get(f"/build/{build_model.name}/{build_model.number}/")

        self.assertEqual(response.status_code, 200)

        expected = {
            "name": build_model.name,
            "number": build_model.number,
            "error": None,
            "storage": {
                "published": False,
                "pulled": False,
            },
            "db": {
                "completed": None,
                "keep": False,
                "note": None,
                "submitted": build_model.submitted.isoformat(),
            },
            "jenkins": {
                "url": (
                    "https://jenkins.invalid/job/"
                    f"{build_model.name}/{build_model.number}/artifact/build.tar.gz"
                ),
            },
        }

        self.assertEqual(response.json(), expected)

    def test_returns_returns_404(self):
        response = self.client.get("/build/bogus/123/")

        self.assertEqual(response.status_code, 404)


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
        buildman = BuildManFactory.build()
        build = buildman.build

        # When we download the artifact
        buildman.publish()

        self.assertTrue(buildman.storage_build.get_path(Content.BINPKGS).exists())
        self.assertTrue(buildman.storage_build.get_path(Content.REPOS).exists())

        response = self.client.post(f"/delete/{build.name}/{build.number}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True, "error": None})

        query = BuildModel.objects.filter(name=build.name, number=build.number)
        self.assertFalse(query.exists())

        exists = [i for i in Content if buildman.storage_build.get_path(i).exists()]

        self.assertFalse(exists)

    def test_build_does_not_exist(self):
        """Should return a 404 response when build does not exist"""
        response = self.client.post("/delete/3000/")

        self.assertEqual(response.status_code, 404)


class DiffBuildsViewTestCase(TempHomeMixin, TestCase):
    """Tests for the diff_builds view"""

    def test(self):
        # Given the first build with tar-1.34
        left_bm = BuildManFactory.build()
        path = left_bm.storage_build.get_path(Content.BINPKGS) / "app-arch" / "tar"
        path.mkdir(parents=True)
        somefile = path / "tar-1.34-1.xpak"
        somefile.write_text("test")

        # Given the second build with tar-1.35
        right_bm = BuildManFactory.build()
        path = right_bm.storage_build.get_path(Content.BINPKGS) / "app-arch" / "tar"
        path.mkdir(parents=True)
        somefile = path / "tar-1.35-1.xpak"
        somefile.write_text("test")

        # When we call get the diff view given the 2 builds
        url = f"/diff/{left_bm.name}/{left_bm.number}/{right_bm.number}/"
        response = self.client.get(url)

        # Then we get a 200 status
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["error"], None)

        # And the differences are given between the two builds
        self.assertEqual(
            data["diff"]["builds"], [left_bm.as_dict(), right_bm.as_dict()]
        )

        self.assertEqual(
            data["diff"]["items"],
            [[-1, "app-arch/tar-1.34-1"], [1, "app-arch/tar-1.35-1"]],
        )


class MachinesViewTestCase(TempHomeMixin, TestCase):
    def test_self(self):
        BuildModelFactory.create_batch(2, name="babette")
        BuildModelFactory.create_batch(3, name="lighthouse")

        response = self.client.get("/machines/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "error": None,
                "machines": [
                    {"name": "babette", "builds": 2},
                    {"name": "lighthouse", "builds": 3},
                ],
            },
        )
