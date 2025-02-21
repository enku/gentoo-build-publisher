"""Unit tests for gbp views"""

# pylint: disable=missing-class-docstring,missing-function-docstring,too-many-ancestors
import datetime as dt
from functools import partial
from typing import Any

from django import urls
from django.http import HttpResponse
from gbp_testkit import DjangoTestCase as BaseTestCase
from unittest_fixtures import Fixtures, fixture, given, where

from gentoo_build_publisher import publisher
from gentoo_build_publisher.types import Build

now = partial(dt.datetime.now, tz=dt.UTC)


@fixture("client")
def lighthouse(_options: Any, fixtures: Fixtures) -> HttpResponse:
    response: HttpResponse = fixtures.client.get("/machines/lighthouse/")
    return response


# pylint: disable=unused-argument
@fixture("publisher", "builds")
def artifacts(_options: Any, fixtures: Fixtures) -> dict[str, Build]:
    artifact_builder = fixtures.publisher.jenkins.artifact_builder
    published = first_build(fixtures.builds, "lighthouse")
    artifact_builder.advance(-86400)
    artifact_builder.build(published, "sys-libs/pam-1.5.3")
    fixtures.publisher.pull(published)
    fixtures.publisher.publish(published)
    latest = latest_build(fixtures.builds, "lighthouse")
    artifact_builder.advance(86400)
    artifact_builder.build(latest, "www-client/firefox-121.0.1")
    publisher.pull(latest)

    return {"published": published, "latest": latest}


@given("publisher", "builds")
@where(
    records_db={"records_backend": "memory"},
    builds={"machines": ["babette", "lighthouse", "web"], "num_days": 3, "per_day": 2},
)
class TestCase(BaseTestCase):
    pass


@given()
class DashboardTestCase(TestCase):
    """Tests for the dashboard view"""

    def test(self, fixtures: Fixtures) -> None:
        publisher.publish(latest_build(fixtures.builds, "lighthouse"))

        # pull the latest web
        publisher.pull(latest_build(fixtures.builds, "web"))

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gentoo_build_publisher/dashboard/main.html")

    def test_can_retrieve_view_by_name(self, fixtures: Fixtures) -> None:
        view = urls.reverse("dashboard")
        self.assertEqual(view, "/")


@given()
class ReposDotConfTestCase(TestCase):
    """Tests for the repos_dot_conf view"""

    def test(self, fixtures: Fixtures) -> None:
        publisher.publish(latest_build(fixtures.builds, "lighthouse"))

        response = self.client.get("/machines/lighthouse/repos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/repos.conf")

    def test_non_published(self, fixtures: Fixtures) -> None:
        publisher.pull(latest_build(fixtures.builds, "lighthouse"))

        response = self.client.get("/machines/lighthouse/repos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_repos_dot_conf(
        self, fixtures: Fixtures
    ) -> None:
        publisher.pull(build := latest_build(fixtures.builds, "lighthouse"))
        publisher.tag(build, "prod")

        response = self.client.get("/machines/lighthouse@prod/repos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/repos.conf")
        self.assertTrue(b"/repos/lighthouse@prod/" in response.content)

    def test_nonexistent_tags_should_return_404(self, fixtures: Fixtures) -> None:
        response = self.client.get("/machines/lighthouse@prod/repos.conf")

        self.assertEqual(response.status_code, 404)


@given()
class BinReposDotConfTestCase(TestCase):
    """Tests for the repos_dot_conf view"""

    def test(self, fixtures: Fixtures) -> None:
        publisher.publish(latest_build(fixtures.builds, "lighthouse"))

        response = self.client.get("/machines/lighthouse/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/binrepos.conf")

    def test_non_published(self, fixtures: Fixtures) -> None:
        publisher.pull(latest_build(fixtures.builds, "lighthouse"))

        response = self.client.get("/machines/lighthouse/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_when_no_such_tag_exists_gives_404(self, fixtures: Fixtures) -> None:
        publisher.pull(latest_build(fixtures.builds, "lighthouse"))

        response = self.client.get("/machines/lighthouse@bogus/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_binrepos_dot_conf(
        self, fixtures: Fixtures
    ) -> None:
        publisher.pull(build := latest_build(fixtures.builds, "lighthouse"))
        publisher.tag(build, "prod")

        response = self.client.get("/machines/lighthouse@prod/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/binrepos.conf")
        self.assertTrue(b"/binpkgs/lighthouse@prod/" in response.content)


@given("publisher", "client", "builds", artifacts, lighthouse)
class MachineViewTests(TestCase):
    """Tests for the machine view"""

    def test_row1(self, fixtures: Fixtures) -> None:
        latest_str = (
            'Latest <span class="badge badge-primary badge-pill">'
            f"{latest_build(fixtures.builds, 'lighthouse').build_id}</span>"
        )
        self.assertContains(fixtures.lighthouse, latest_str)

        published_str = (
            'Published <span class="badge badge-primary badge-pill">'
            f"{fixtures.artifacts['published'].build_id}</span>"
        )
        self.assertContains(fixtures.lighthouse, published_str)

    def test_returns_404_on_nonbuild_machines(self, fixtures: Fixtures) -> None:
        response = self.client.get("/machines/bogus/")

        self.assertEqual(response.status_code, 404)


@given(artifacts)
class BinPkgViewTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        package = fixtures.artifacts["latest"]
        client = self.client
        url = (
            f"/machines/lighthouse/builds/{package.build_id}/"
            "packages/sys-libs/pam/pam-1.5.3-1"
        )
        response = client.get(url)

        self.assertEqual(response.status_code, 301, response.content)

        request = response.request
        expected = (
            f"/binpkgs/lighthouse.{package.build_id}/sys-libs/pam/pam-1.5.3-1.gpkg.tar"
        )
        self.assertTrue(response["Location"].endswith(expected), response["Location"])

    def test_when_build_does_not_exist(self, fixtures: Fixtures) -> None:
        client = self.client
        url = "/machines/bogus/builds/2/packages/x11-apps/xhost/xhost-1.0.10-1"

        response = client.get(url)

        self.assertEqual(response.status_code, 404, response.content)

    def test_when_pkg_does_not_exist(self, fixtures: Fixtures) -> None:
        package = fixtures.artifacts["latest"]

        client = self.client
        url = (
            f"/machines/lighthouse/builds/{package.build_id}/"
            "packages/x11-apps/xhost/xhost-1.0.10-1"
        )
        response = client.get(url)

        self.assertEqual(response.status_code, 404, response.content)


def first_build(build_dict: dict[str, list[Build]], name: str) -> Build:
    return build_dict[name][0]


def latest_build(build_dict: dict[str, list[Build]], name: str) -> Build:
    return build_dict[name][-1]
