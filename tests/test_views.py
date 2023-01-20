"""Unit tests for gbp views"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from collections import defaultdict

from django.utils import timezone

from gentoo_build_publisher.publisher import MachineInfo
from gentoo_build_publisher.types import Content
from gentoo_build_publisher.views import (
    get_build_summary,
    get_metadata,
    get_packages,
    package_metadata,
)

from . import QuickCache, TestCase
from .factories import BuildFactory


class GetPackagesTestCase(TestCase):
    """This is just cached Build.get_packages()"""

    def test(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        self.publisher.pull(build)

        packages = get_packages(build, cache)

        self.assertEqual(packages, self.publisher.get_packages(build))
        self.assertEqual(cache.cache, {f"packages-{build}": packages})

    def test_when_cached_return_cache(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        cache.set(f"packages-{build}", [1, 2, 3])  # not real packages

        packages = get_packages(build, cache)

        self.assertEqual(packages, [1, 2, 3])


class GetBuildSummaryTestCase(TestCase):
    def test(self) -> None:
        now = timezone.now()
        machines = ["babette", "lighthouse", "web"]
        builds = BuildFactory.buncha_builds(machines, now, 3, 2)

        lighthouse = builds["lighthouse"][-1]
        for cpv in [
            "acct-group/sgx-0",
            "app-admin/perl-cleaner-2.30",
            "app-crypt/gpgme-1.14.0",
        ]:
            self.artifact_builder.build(lighthouse, cpv)
        self.publisher.publish(lighthouse)

        web = builds["web"][-1]
        self.publisher.pull(web)

        # Make sure it doesn't fail when a gbp.json is missing
        (self.publisher.storage.get_path(web, Content.BINPKGS) / "gbp.json").unlink()

        machine_info = [MachineInfo(i) for i in machines]

        # Make sure it doesn't fail when a machine has no latest build (i.e. being built
        # for the first time)
        machine_info.append(MachineInfo("foo"))

        result = get_build_summary(now, machine_info)

        self.assertEqual(
            result.latest_builds,
            [self.publisher.record(lighthouse), self.publisher.record(web)],
        )
        self.assertEqual(
            result.built_recently,
            [self.publisher.record(lighthouse), self.publisher.record(web)],
        )
        self.assertEqual(
            result.latest_published, set([self.publisher.record(lighthouse)])
        )
        pkgs = [
            "acct-group/sgx-0",
            "app-admin/perl-cleaner-2.30",
            "app-crypt/gpgme-1.14.0",
        ]
        self.assertEqual(result.build_packages, {str(lighthouse): pkgs, str(web): []})


class PackageMetadataTestCase(TestCase):
    def test(self) -> None:
        now = timezone.now()
        build = BuildFactory()

        for cpv in ["dev-vcs/git-2.34.1", "app-portage/gentoolkit-0.5.1-r1"]:
            self.artifact_builder.build(build, cpv)

        self.publisher.pull(build)
        record = self.publisher.record(build)
        context = {
            "now": now,
            "package_count": 0,
            "package_sizes": defaultdict(int),
            "recent_packages": defaultdict(set),
            "total_package_size": defaultdict(int),
        }
        package_metadata(record, context)

        expected = {
            "now": now,
            "package_count": 6,
            "package_sizes": defaultdict(int, {}),
            "recent_packages": defaultdict(
                set,
                {
                    "dev-vcs/git-2.34.1": {"babette"},
                    "app-portage/gentoolkit-0.5.1-r1": {"babette"},
                },
            ),
            "total_package_size": defaultdict(int, {"babette": 3238}),
        }

        self.assertEqual(context, expected)


class DashboardTestCase(TestCase):
    """Tests for the dashboard view"""

    def setUp(self) -> None:
        super().setUp()

        self.now = timezone.now()
        self.machines = ["babette", "lighthouse", "web"]
        self.builds = BuildFactory.buncha_builds(self.machines, self.now, 3, 2)

    def test(self) -> None:
        lighthouse = self.builds["lighthouse"][-1]
        self.publisher.publish(lighthouse)

        # pull the latest web
        web = self.builds["web"][-1]
        self.publisher.pull(web)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gentoo_build_publisher/dashboard.html")


class ReposDotConfTestCase(TestCase):
    """Tests for the repos_dot_conf view"""

    def setUp(self) -> None:
        super().setUp()

        self.now = timezone.now()
        self.machines = ["babette", "lighthouse", "web"]
        self.builds = BuildFactory.buncha_builds(self.machines, self.now, 3, 2)

    def test(self) -> None:
        machine = "lighthouse"
        build = self.builds[machine][-1]
        self.publisher.publish(build)

        response = self.client.get(f"/machines/{machine}/repos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/repos.conf")

    def test_non_published(self) -> None:
        machine = "lighthouse"
        build = self.builds[machine][-1]
        self.publisher.pull(build)

        response = self.client.get(f"/machines/{machine}/repos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_repos_dot_conf(self) -> None:
        machine = "lighthouse"
        build = self.builds[machine][-1]
        self.publisher.pull(build)
        self.publisher.tag(build, "prod")

        response = self.client.get("/machines/lighthouse@prod/repos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/repos.conf")
        self.assertTrue(b"/repos/lighthouse@prod/" in response.content)

    def test_nonexistant_tags_should_return_404(self) -> None:
        response = self.client.get("/machines/lighthouse@prod/repos.conf")

        self.assertEqual(response.status_code, 404)


class BinReposDotConfTestCase(TestCase):
    """Tests for the repos_dot_conf view"""

    def setUp(self) -> None:
        super().setUp()

        self.now = timezone.now()
        self.machines = ["babette", "lighthouse", "web"]
        self.builds = BuildFactory.buncha_builds(self.machines, self.now, 3, 2)

    def test(self) -> None:
        machine = "lighthouse"
        build = self.builds[machine][-1]
        self.publisher.publish(build)

        response = self.client.get(f"/machines/{machine}/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/binrepos.conf")

    def test_non_published(self) -> None:
        machine = "lighthouse"
        build = self.builds[machine][-1]
        self.publisher.pull(build)

        response = self.client.get(f"/machines/{machine}/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_when_no_such_tag_exists_gives_404(self) -> None:
        machine = "lighthouse"
        build = self.builds[machine][-1]
        self.publisher.pull(build)

        response = self.client.get(f"/machines/{machine}@bogus/binrepos.conf")

        self.assertEqual(response.status_code, 404)

    def test_tagged_builds_should_have_a_binrepos_dot_conf(self) -> None:
        machine = "lighthouse"
        build = self.builds[machine][-1]
        self.publisher.pull(build)
        self.publisher.tag(build, "prod")

        response = self.client.get("/machines/lighthouse@prod/binrepos.conf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertTemplateUsed(response, "gentoo_build_publisher/binrepos.conf")
        self.assertTrue(b"/binpkgs/lighthouse@prod/" in response.content)


class GetMetadataTestCase(TestCase):
    """This is just cached Storage.get_metadata()"""

    def test(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        self.publisher.pull(build)

        metadata = get_metadata(build, cache)

        self.assertEqual(metadata, self.publisher.storage.get_metadata(build))
        self.assertEqual(cache.cache, {f"metadata-{build}": metadata})

    def test_when_cached_return_cache(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        cache.set(f"metadata-{build}", [1, 2, 3])  # not real metadata

        metadata = get_metadata(build, cache)

        self.assertEqual(metadata, [1, 2, 3])
