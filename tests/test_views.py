"""Unit tests for gbp views"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
from collections import defaultdict

from django.utils import timezone

from gentoo_build_publisher.build import BuildID, Content
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import BuildPublisher, MachineInfo
from gentoo_build_publisher.views import (
    get_build_summary,
    get_packages,
    package_metadata,
)

from . import TestCase
from .factories import BuildIDFactory, BuildPublisherFactory


def buncha_builds(
    build_publisher: BuildPublisher,
    machines: list[str],
    end_date,
    num_days: int,
    per_day: int,
) -> defaultdict[str, list[BuildID]]:
    buildmap = defaultdict(list)

    for i in reversed(range(num_days)):
        day = end_date - dt.timedelta(days=i)
        for name in machines:
            build_ids = BuildIDFactory.create_batch(per_day, name=name)

            for build_id in build_ids:
                BuildDB.save(build_publisher.record(build_id), submitted=day)

            buildmap[name].extend(build_ids)
    return buildmap


class GetPackagesTestCase(TestCase):
    """This is just cached Build.get_packages()"""

    def test(self):
        build_publisher = BuildPublisherFactory()
        build_id = BuildIDFactory()
        build_publisher.pull(build_id)

        packages = get_packages(build_id)

        self.assertEqual(packages, build_publisher.get_packages(build_id))


class GetBuildSummaryTestCase(TestCase):
    def test(self):
        build_publisher = BuildPublisherFactory()
        now = timezone.now()
        machines = ["babette", "lighthouse", "web"]
        builds = buncha_builds(build_publisher, machines, now, 3, 2)

        lighthouse = builds["lighthouse"][-1]
        build_publisher.publish(lighthouse)

        web = builds["web"][-1]
        build_publisher.pull(web)

        # Make sure it doesn't fail when a gbp.json is missing
        (build_publisher.storage.get_path(web, Content.BINPKGS) / "gbp.json").unlink()

        machine_info = [MachineInfo(i) for i in machines]

        # Make sure it doesn't fail when a machine has no latest build (i.e. being built
        # for the first time)
        machine_info.append(MachineInfo("foo"))

        result = get_build_summary(now, machine_info)
        latest_builds, built_recently, build_packages, latest_published = result

        self.assertEqual(latest_builds, [lighthouse, web])
        self.assertEqual(built_recently, [lighthouse, web])
        self.assertEqual(latest_published, set([lighthouse]))
        pkgs = [
            "acct-group/sgx-0",
            "app-admin/perl-cleaner-2.30",
            "app-crypt/gpgme-1.14.0",
        ]
        self.assertEqual(build_packages, {str(lighthouse): pkgs, str(web): []})


class PackageMetadataTestCase(TestCase):
    def test(self):
        now = timezone.now()
        build_id = BuildIDFactory()
        build_publisher = BuildPublisherFactory()
        build_publisher.pull(build_id)
        context = {
            "now": now,
            "package_count": 0,
            "package_sizes": defaultdict(int),
            "recent_packages": defaultdict(set),
            "total_package_size": defaultdict(int),
        }
        package_metadata(build_id, context)

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
        self.build_publisher = BuildPublisherFactory()
        self.builds = buncha_builds(self.build_publisher, self.machines, self.now, 3, 2)

    def test(self):
        lighthouse = self.builds["lighthouse"][-1]
        self.build_publisher.publish(lighthouse)

        # pull the latest web
        web = self.builds["web"][-1]
        self.build_publisher.pull(web)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gentoo_build_publisher/dashboard.html")
