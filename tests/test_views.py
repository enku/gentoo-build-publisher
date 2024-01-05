"""Unit tests for gbp views"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
from functools import partial

from gentoo_build_publisher.common import Build

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
        self.publisher.publish(self.latest_build("lighthouse"))

        # pull the latest web
        self.publisher.pull(self.latest_build("web"))

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gentoo_build_publisher/dashboard/main.html")


class ReposDotConfTestCase(TestCase):
    """Tests for the repos_dot_conf view"""

    def test(self) -> None:
        self.publisher.publish(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse/repos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/repos.conf")

    def test_non_published(self) -> None:
        self.publisher.pull(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse/repos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_repos_dot_conf(self) -> None:
        self.publisher.pull(build := self.latest_build("lighthouse"))
        self.publisher.tag(build, "prod")

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
        self.publisher.publish(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/binrepos.conf")

    def test_non_published(self) -> None:
        self.publisher.pull(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_when_no_such_tag_exists_gives_404(self) -> None:
        self.publisher.pull(self.latest_build("lighthouse"))

        response = self.client.get("/machines/lighthouse@bogus/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_binrepos_dot_conf(self) -> None:
        self.publisher.pull(build := self.latest_build("lighthouse"))
        self.publisher.tag(build, "prod")

        response = self.client.get("/machines/lighthouse@prod/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/binrepos.conf")
        self.assertTrue(b"/binpkgs/lighthouse@prod/" in response.content)
