"""Unit tests for gbp views"""

# pylint: disable=missing-class-docstring,missing-function-docstring,too-many-ancestors
import datetime as dt
from functools import partial

from django import urls
from django.http import HttpResponse
from unittest_fixtures import Fixtures, fixture, given, where

import gbp_testkit.fixtures as testkit
from gbp_testkit import DjangoTestCase as BaseTestCase
from gentoo_build_publisher import publisher
from gentoo_build_publisher.types import Build

now = partial(dt.datetime.now, tz=dt.UTC)


@fixture(testkit.client)
def lighthouse(fixtures: Fixtures) -> HttpResponse:
    response: HttpResponse = fixtures.client.get("/machines/lighthouse/")
    return response


# pylint: disable=unused-argument
@fixture(testkit.publisher, testkit.builds)
def artifacts(fixtures: Fixtures) -> dict[str, Build]:
    artifact_builder = publisher.jenkins.artifact_builder
    published = first_build(fixtures.builds, "lighthouse")
    artifact_builder.advance(-86400)
    artifact_builder.build(published, "sys-libs/pam-1.5.3")
    publisher.pull(published)
    publisher.publish(published)
    latest = latest_build(fixtures.builds, "lighthouse")
    artifact_builder.advance(86400)
    artifact_builder.build(latest, "www-client/firefox-121.0.1")
    publisher.pull(latest)

    return {"published": published, "latest": latest}


@given(testkit.publisher, testkit.builds)
@where(
    records_db__backend="memory",
    builds__machines=["babette", "lighthouse", "web"],
    builds__num_days=3,
    builds__per_day=2,
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


@given(testkit.publisher, testkit.client, testkit.builds, artifacts, lighthouse)
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


@given(testkit.publisher, testkit.client, testkit.builds, artifacts)
class BuildViewTests(TestCase):
    """Tests for the build view"""

    def test_responds_with_rendered_template(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        builds = fixtures.builds
        build = builds["lighthouse"][-1]
        url = f"/machines/lighthouse/builds/{build.build_id}/"

        response = client.get(url)

        self.assertEqual(200, response.status_code)
        template = response.templates[0]
        self.assertEqual("gentoo_build_publisher/build/main.html", template.name)

    def test_given_tag(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        builds = fixtures.builds
        build = builds["lighthouse"][-1]
        publisher.tag(build, "test")
        url = "/machines/lighthouse/builds/@test/"

        response = client.get(url)

        self.assertEqual(
            302, response.status_code, "Did not respond with temporary redirect"
        )
        self.assertEqual(
            f"/machines/lighthouse/builds/{build.build_id}/",
            response["Location"],
            "Redirect was not the expected URL",
        )

    def test_given_tag_does_not_exist(self, fixtures: Fixtures) -> None:
        client = fixtures.client

        response = client.get("/machines/lighthouse/builds/@bogus/")

        self.assertEqual(404, response.status_code, "Did not respond with 404")

    def test_published_tag(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        builds = fixtures.builds
        build = builds["lighthouse"][-1]
        publisher.publish(build)
        url = "/machines/lighthouse/builds/@/"

        response = client.get(url)

        self.assertEqual(
            302, response.status_code, "Did not respond with temporary redirect"
        )
        self.assertEqual(
            f"/machines/lighthouse/builds/{build.build_id}/",
            response["Location"],
            "Redirect was not the expected URL",
        )

    def test_404_response(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        url = "/machines/bogus/builds/xxx/"

        response = client.get(url)

        self.assertEqual(404, response.status_code)


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


@given(testkit.plugins)
class AboutViewTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        client = self.client
        response = client.get("/about/")

        for plugin in fixtures.plugins:
            with self.subTest(plugin=plugin.name):
                self.assertContains(response, f'<th scope="row">{plugin.name}</th>')

        self.assertTemplateUsed(response, "gentoo_build_publisher/about/main.html")


def first_build(build_dict: dict[str, list[Build]], name: str) -> Build:
    return build_dict[name][0]


def latest_build(build_dict: dict[str, list[Build]], name: str) -> Build:
    return build_dict[name][-1]
