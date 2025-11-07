"""Unit tests for gbp views"""

# pylint: disable=missing-class-docstring,missing-function-docstring,too-many-ancestors
import datetime as dt
from functools import partial
from unittest import TestCase as BaseTestCase

from django import urls
from django.http import HttpResponse
from unittest_fixtures import Fixtures, fixture, given, params, where

import gbp_testkit.fixtures as testkit
from gentoo_build_publisher.cache import clear as cache_clear
from gentoo_build_publisher.types import Build, Content
from gentoo_build_publisher.utils import string

__unittest = True  # pylint: disable=invalid-name
now = partial(dt.datetime.now, tz=dt.UTC)


@fixture(testkit.client)
def lighthouse(fixtures: Fixtures) -> HttpResponse:
    response: HttpResponse = fixtures.client.get("/machines/lighthouse/")
    return response


# pylint: disable=unused-argument
@fixture(testkit.publisher, testkit.builds)
def artifacts(fixtures: Fixtures) -> dict[str, Build]:
    publisher = fixtures.publisher
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
    builds__machines=["babette", "lighthouse", "web"],
    builds__num_days=3,
    builds__per_day=2,
)
class TestCase(BaseTestCase):
    def assert_template_used(self, name: str, response: HttpResponse) -> None:
        self.assertIn(name, [i.name for i in response.templates])  # type: ignore[attr-defined]

    def assert_contains(self, expected: str, response: HttpResponse) -> None:
        self.assertIn(expected, response.text)


@given(testkit.client)
class DashboardTestCase(TestCase):
    """Tests for the dashboard view"""

    def test(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        publisher.publish(latest_build(fixtures.builds, "lighthouse"))

        # pull the latest web
        publisher.pull(latest_build(fixtures.builds, "web"))

        response = fixtures.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assert_template_used(
            "gentoo_build_publisher/dashboard/main.html", response
        )
        self.assert_template_used("gentoo_build_publisher/footerlink.html", response)

    def test_can_retrieve_view_by_name(self, fixtures: Fixtures) -> None:
        view = urls.reverse("dashboard")
        self.assertEqual(view, "/")


@given(testkit.client)
class ReposDotConfTestCase(TestCase):
    """Tests for the repos_dot_conf view"""

    def test(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        publisher.publish(latest_build(fixtures.builds, "lighthouse"))

        response = fixtures.client.get("/machines/lighthouse/repos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assert_template_used("gentoo_build_publisher/repos.conf", response)

    def test_non_published(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        publisher.pull(latest_build(fixtures.builds, "lighthouse"))

        response = fixtures.client.get("/machines/lighthouse/repos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_repos_dot_conf(
        self, fixtures: Fixtures
    ) -> None:
        publisher = fixtures.publisher
        publisher.pull(build := latest_build(fixtures.builds, "lighthouse"))
        publisher.tag(build, "prod")

        response = fixtures.client.get("/machines/lighthouse@prod/repos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assert_template_used("gentoo_build_publisher/repos.conf", response)
        self.assertTrue(b"/repos/lighthouse@prod/" in response.content)

    def test_nonexistent_tags_should_return_404(self, fixtures: Fixtures) -> None:
        response = fixtures.client.get("/machines/lighthouse@prod/repos.conf")

        self.assertEqual(response.status_code, 404)


@given(testkit.client)
class BinReposDotConfTestCase(TestCase):
    """Tests for the repos_dot_conf view"""

    def test(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        publisher.publish(latest_build(fixtures.builds, "lighthouse"))

        response = fixtures.client.get("/machines/lighthouse/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assert_template_used("gentoo_build_publisher/binrepos.conf", response)

    def test_non_published(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        publisher.pull(latest_build(fixtures.builds, "lighthouse"))

        response = fixtures.client.get("/machines/lighthouse/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_when_no_such_tag_exists_gives_404(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        publisher.pull(latest_build(fixtures.builds, "lighthouse"))

        response = fixtures.client.get("/machines/lighthouse@bogus/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_binrepos_dot_conf(
        self, fixtures: Fixtures
    ) -> None:
        publisher = fixtures.publisher
        publisher.pull(build := latest_build(fixtures.builds, "lighthouse"))
        publisher.tag(build, "prod")

        response = fixtures.client.get("/machines/lighthouse@prod/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assert_template_used("gentoo_build_publisher/binrepos.conf", response)
        self.assertTrue(b"/binpkgs/lighthouse@prod/" in response.content)


@given(testkit.publisher, testkit.client, testkit.builds, artifacts, lighthouse)
@given(clear_cache=lambda _: cache_clear())
class MachineViewTests(TestCase):
    """Tests for the machine view"""

    def test_row1(self, fixtures: Fixtures) -> None:
        latest_str = (
            'Latest <span class="badge badge-primary badge-pill">'
            f"{latest_build(fixtures.builds, 'lighthouse').build_id}</span>"
        )
        self.assert_contains(latest_str, fixtures.lighthouse)

        published_str = (
            'Published <span class="badge badge-primary badge-pill">'
            f"{fixtures.artifacts['published'].build_id}</span>"
        )
        self.assert_contains(published_str, fixtures.lighthouse)

    def test_returns_404_on_nonbuild_machines(self, fixtures: Fixtures) -> None:
        response = fixtures.client.get("/machines/bogus/")

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

    def test_package_links(self, fixtures: Fixtures) -> None:
        build = fixtures.builds["lighthouse"][-1]
        url = f"/machines/lighthouse/builds/{build.build_id}/"
        publisher = fixtures.publisher

        response = fixtures.client.get(url)

        metadata = publisher.build_metadata(build)
        packages = metadata.packages
        package = packages.built[-1]
        cpv = string.split_pkg(package.cpv)
        expected = (
            '<a target="_blank" class="package-link external-link" '
            f'href="https://packages.gentoo.org/packages/{cpv[0]}/{cpv[1]}"'
            f">{package.cpv}</a>"
        )
        self.assertIn(expected, response.text)

    def test_given_tag(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        builds = fixtures.builds
        build = builds["lighthouse"][-1]
        publisher = fixtures.publisher
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
        publisher = fixtures.publisher
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

    def test_build_note(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        builds = fixtures.builds
        build = builds["lighthouse"][-1]
        publisher = fixtures.publisher
        record = publisher.repo.build_records.get(build)
        publisher.repo.build_records.save(record, note="This is a build note")
        url = f"/machines/lighthouse/builds/{build.build_id}/"

        response = client.get(url)

        expected = r'<div id="build-note">\s*<pre>This is a build note</pre>\s*</div>'
        self.assertRegex(response.text, expected, "Note not found in response")

    def test_no_build_note(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        builds = fixtures.builds
        build = builds["lighthouse"][-1]
        url = f"/machines/lighthouse/builds/{build.build_id}/"

        response = client.get(url)

        self.assertNotIn("build-note", response.text)

    def test_404_response(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        url = "/machines/bogus/builds/xxx/"

        response = client.get(url)

        self.assertEqual(404, response.status_code)

    def test_missing_gbp_json(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        builds = fixtures.builds
        build = builds["lighthouse"][-1]
        publisher = fixtures.publisher
        url = f"/machines/lighthouse/builds/{build.build_id}/"
        gbp_json = publisher.storage.get_path(build, Content.BINPKGS) / "gbp.json"
        gbp_json.unlink()

        response = client.get(url)

        self.assertEqual(200, response.status_code)


@given(artifacts, testkit.client)
@params(view=("logs.txt", "logs/"))
class LogsTests(TestCase):
    def test_gets_logs(self, fixtures: Fixtures) -> None:
        build = fixtures.artifacts["latest"]
        publisher = fixtures.publisher
        record = publisher.repo.build_records.get(build)

        url = f"/machines/{build.machine}/builds/{build.build_id}/{fixtures.view}"
        client = fixtures.client
        response = client.get(url)

        self.assertEqual(response.status_code, 200)

        if fixtures.view == "logs.txt":
            self.assertEqual(response.text, record.logs)
            self.assertEqual(response["Content-Type"], "text/plain")
        else:
            self.assertIn(
                "gentoo_build_publisher/build/logs.html",
                [i.name for i in response.templates],
            )

    def test_404(self, fixtures: Fixtures) -> None:
        client = fixtures.client

        response = client.get(f"/machines/bogus/builds/123/{fixtures.view}")

        self.assertEqual(response.status_code, 404)

    def test_given_tag(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        build = fixtures.artifacts["latest"]
        publisher = fixtures.publisher
        publisher.tag(build, "test")
        url = f"/machines/lighthouse/builds/@test/{fixtures.view}"

        response = client.get(url)

        self.assertEqual(
            302, response.status_code, "Did not respond with temporary redirect"
        )
        self.assertEqual(
            f"/machines/lighthouse/builds/{build.build_id}/{fixtures.view}",
            response["Location"],
            "Redirect was not the expected URL",
        )

    def test_given_tag_does_not_exist(self, fixtures: Fixtures) -> None:
        client = fixtures.client

        response = client.get(f"/machines/lighthouse/builds/@bogus/{fixtures.view}")

        self.assertEqual(404, response.status_code, "Did not respond with 404")

    def test_published_tag(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        build = fixtures.artifacts["latest"]
        publisher = fixtures.publisher
        publisher.publish(build)
        url = f"/machines/lighthouse/builds/@/{fixtures.view}"

        response = client.get(url)

        self.assertEqual(
            302, response.status_code, "Did not respond with temporary redirect"
        )
        self.assertEqual(
            f"/machines/lighthouse/builds/{build.build_id}/{fixtures.view}",
            response["Location"],
            "Redirect was not the expected URL",
        )


@given(artifacts, testkit.client)
class BinPkgViewTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        package = fixtures.artifacts["latest"]
        client = fixtures.client
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
        client = fixtures.client
        url = "/machines/bogus/builds/2/packages/x11-apps/xhost/xhost-1.0.10-1"

        response = client.get(url)

        self.assertEqual(response.status_code, 404, response.content)

    def test_when_pkg_does_not_exist(self, fixtures: Fixtures) -> None:
        package = fixtures.artifacts["latest"]

        client = fixtures.client
        url = (
            f"/machines/lighthouse/builds/{package.build_id}/"
            "packages/x11-apps/xhost/xhost-1.0.10-1"
        )
        response = client.get(url)

        self.assertEqual(response.status_code, 404, response.content)


@given(testkit.plugins, testkit.client)
class AboutViewTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        response = client.get("/about/")

        for plugin in fixtures.plugins:
            with self.subTest(plugin=plugin.name):
                self.assertIn(f'<th scope="row">{plugin.name}</th>', response.text)

        self.assert_template_used("gentoo_build_publisher/about/main.html", response)


@given(testkit.client)
@given(links=testkit.patch)
@where(
    links__target=(
        "gentoo_build_publisher.django."
        "gentoo_build_publisher.templatetags.gbp.FOOTER_LINKS"
    )
)
@where(links__new={"Google": "https://www.google.com/", "Test": "http://test.com/"})
class FooterTests(TestCase):
    def test_footer_links_from_settings(self, fixtures: Fixtures) -> None:
        client = fixtures.client

        response = client.get("/")
        html = response.text

        expected = """<a href="https://www.google.com/">Google</a>"""
        self.assertIn(expected, html)

        expected = """<a href="http://test.com/">Test</a>"""
        self.assertIn(expected, html)


def first_build(build_dict: dict[str, list[Build]], name: str) -> Build:
    return build_dict[name][0]


def latest_build(build_dict: dict[str, list[Build]], name: str) -> Build:
    return build_dict[name][-1]
