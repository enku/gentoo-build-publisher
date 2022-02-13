"""Unit tests for gbp views"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
from collections import defaultdict

from django.utils import timezone

from gentoo_build_publisher.build import Content
from gentoo_build_publisher.managers import BuildMan, MachineInfo
from gentoo_build_publisher.views import (
    get_build_summary,
    get_packages,
    package_metadata,
)

from . import TestCase
from .factories import BuildManFactory


def buncha_builds(
    machines: list[str], end_date, num_days: int, per_day: int
) -> defaultdict[str, list[BuildMan]]:
    buildmans = defaultdict(list)

    for i in reversed(range(num_days)):
        day = end_date - dt.timedelta(days=i)
        for name in machines:
            builds = BuildManFactory.create_batch(
                per_day,
                build_attr__build_model__submitted=day,
                build_attr__build_model__name=name,
            )
            buildmans[name].extend(builds)
    return buildmans


class GetPackagesTestCase(TestCase):
    """This is just cached BuildMan.get_packages()"""

    def test(self):
        buildman = BuildManFactory.create()
        buildman.pull()

        packages = get_packages(buildman)

        self.assertEqual(packages, buildman.get_packages())


class GetBuildSummaryTestCase(TestCase):
    def test(self):
        now = timezone.now()
        machines = ["babette", "lighthouse", "web"]
        builds = buncha_builds(machines, now, 3, 2)

        lighthouse = builds["lighthouse"][-1]
        lighthouse.publish()

        web = builds["web"][-1]
        web.pull()

        # Make sure it doesn't fail when a gbp.json is missing
        (web.storage.get_path(web.build.id, Content.BINPKGS) / "gbp.json").unlink()

        machine_info = [MachineInfo(i) for i in machines]

        # Make sure it doesn't fail when a machine has no latest build (i.e. being built
        # for the first time)
        machine_info.append(MachineInfo("foo"))

        result = get_build_summary(now, machine_info)
        latest_builds, built_recently, build_packages = result

        self.assertEqual(latest_builds, [lighthouse, web])
        self.assertEqual(built_recently, [lighthouse, web])
        pkgs = [
            "acct-group/sgx-0",
            "app-admin/perl-cleaner-2.30",
            "app-crypt/gpgme-1.14.0",
        ]
        self.assertEqual(build_packages, {str(lighthouse): pkgs, str(web): []})


class PackageMetadataTestCase(TestCase):
    def test(self):
        now = timezone.now()
        buildman = BuildManFactory.create()
        buildman.pull()
        context = {
            "now": now,
            "package_count": 0,
            "package_sizes": defaultdict(int),
            "recent_packages": defaultdict(set),
            "total_package_size": defaultdict(int),
        }
        package_metadata(buildman, context)

        expected = {
            "now": now,
            "package_count": 4,
            "package_sizes": defaultdict(int, {}),
            "recent_packages": defaultdict(
                set,
                {
                    "acct-group/sgx-0": {"babette"},
                    "app-admin/perl-cleaner-2.30": {"babette"},
                    "app-crypt/gpgme-1.14.0": {"babette"},
                },
            ),
            "total_package_size": defaultdict(int, {"babette": 889824}),
        }

        self.assertEqual(context, expected)


class DashboardTestCase(TestCase):
    """Tests for the dashboard view"""

    def setUp(self):
        super().setUp()

        self.now = timezone.now()
        self.machines = ["babette", "lighthouse", "web"]
        self.builds = buncha_builds(self.machines, self.now, 3, 2)

    def test(self):
        lighthouse = self.builds["lighthouse"][-1]
        lighthouse.publish()

        # pull the latest web
        web = self.builds["web"][-1]
        web.pull()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gentoo_build_publisher/dashboard.html")
