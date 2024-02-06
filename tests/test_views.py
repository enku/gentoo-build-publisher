"""Unit tests for gbp views"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
from functools import partial
from unittest import mock

from django import urls
from django.http import Http404, HttpRequest, HttpResponse

from gentoo_build_publisher import publisher
from gentoo_build_publisher.common import Build
from gentoo_build_publisher.views import experimental

from . import DjangoTestCase as BaseTestCase
from .factories import BuildFactory

now = partial(dt.datetime.now, tz=dt.UTC)


class TestCase(BaseTestCase):
    RECORDS_BACKEND = "memory"

    def setUp(self) -> None:
        super().setUp()

        self.now = now()
        self.machines = ["babette", "lighthouse", "web"]
        self.builds = BuildFactory.buncha_builds(self.machines, self.now, 3, 2)

    def first_build(self, name: str) -> Build:
        return self.builds[name][0]

    def latest_build(self, name: str) -> Build:
        return self.builds[name][-1]


class DashboardTestCase(TestCase):
    """Tests for the dashboard view"""

    def test(self) -> None:
        publisher.publish(self.latest_build("lighthouse"))

        # pull the latest web
        publisher.pull(self.latest_build("web"))

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gentoo_build_publisher/dashboard/main.html")

    def test_can_retrieve_view_by_name(self) -> None:
        view = urls.reverse("dashboard")
        self.assertEqual(view, "/")


class ReposDotConfTestCase(TestCase):
    """Tests for the repos_dot_conf view"""

    def test(self) -> None:
        publisher.publish(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse/repos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/repos.conf")

    def test_non_published(self) -> None:
        publisher.pull(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse/repos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_repos_dot_conf(self) -> None:
        publisher.pull(build := self.latest_build("lighthouse"))
        publisher.tag(build, "prod")

        response = self.client.get("/machines/lighthouse@prod/repos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/repos.conf")
        self.assertTrue(b"/repos/lighthouse@prod/" in response.content)

    def test_nonexistent_tags_should_return_404(self) -> None:
        response = self.client.get("/machines/lighthouse@prod/repos.conf")

        self.assertEqual(response.status_code, 404)


class BinReposDotConfTestCase(TestCase):
    """Tests for the repos_dot_conf view"""

    def test(self) -> None:
        publisher.publish(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/binrepos.conf")

    def test_non_published(self) -> None:
        publisher.pull(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_when_no_such_tag_exists_gives_404(self) -> None:
        publisher.pull(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse@bogus/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_binrepos_dot_conf(self) -> None:
        publisher.pull(build := self.latest_build("lighthouse"))
        publisher.tag(build, "prod")

        response = self.client.get("/machines/lighthouse@prod/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/binrepos.conf")
        self.assertTrue(b"/binpkgs/lighthouse@prod/" in response.content)


class MachineViewTests(TestCase):
    """Tests for the machine view"""

    def setUp(self) -> None:
        super().setUp()
        self.published = self.first_build("lighthouse")
        self.artifact_builder.advance(-86400)
        self.artifact_builder.build(self.published, "sys-libs/pam-1.5.3")
        publisher.pull(self.published)
        publisher.publish(self.published)
        self.latest = self.latest_build("lighthouse")
        self.artifact_builder.advance(86400)
        self.artifact_builder.build(self.latest, "www-client/firefox-121.0.1")
        publisher.pull(self.latest)

        self.response = self.client.get("/machines/lighthouse/")

    def test_row1(self) -> None:
        latest_str = (
            'Latest <span class="badge badge-primary badge-pill">'
            f"{self.latest.build_id}</span>"
        )
        self.assertContains(self.response, latest_str)

        published_str = (
            'Published <span class="badge badge-primary badge-pill">'
            f"{self.published.build_id}</span>"
        )
        self.assertContains(self.response, published_str)

    def test_returns_404_on_nonbuild_machines(self) -> None:
        response = self.client.get("/machines/bogus/")

        self.assertEqual(response.status_code, 404)


class ExperimentalMarkerTests(TestCase):
    def test_debug_is_false(self) -> None:
        request = mock.MagicMock(spec=HttpRequest)
        experimental_view = experimental(dummy_view)

        with self.settings(DEBUG=False):
            response = dummy_view(request)
            self.assertEqual(response.status_code, 200)

            with self.assertRaises(Http404):
                response = experimental_view(request)

    def test_debug_is_true(self) -> None:
        request = mock.MagicMock(spec=HttpRequest)
        experimental_view = experimental(dummy_view)

        with self.settings(DEBUG=True):
            response = dummy_view(request)
            self.assertEqual(response.status_code, 200)

            response = experimental_view(request)
            self.assertEqual(response.status_code, 200)


def dummy_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("Hi!")
