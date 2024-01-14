"""Tests for the dashboard utils"""
# pylint: disable=missing-docstring
import datetime as dt
from typing import cast
from unittest import mock

from gentoo_build_publisher.common import Build, Content
from gentoo_build_publisher.publisher import MachineInfo
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.views import (
    DashboardContext,
    ViewInputContext,
    add_package_metadata,
    create_dashboard_context,
    get_build_summary,
    get_machine_recent_packages,
    get_metadata,
    get_packages,
    get_query_value_from_request,
)

from . import QuickCache, TestCase
from .factories import BuildFactory, BuildRecordFactory, package_factory


class GetPackagesTestCase(TestCase):
    """This is just cached Build.get_packages()"""

    def test(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        self.publisher.pull(build)

        packages = get_packages(build, self.publisher, cache)

        self.assertEqual(packages, self.publisher.get_packages(build))
        self.assertEqual(cache.cache, {f"packages-{build}": packages})

    def test_when_cached_return_cache(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        cache.set(f"packages-{build}", [1, 2, 3])  # not real packages

        packages = get_packages(build, self.publisher, cache)

        self.assertEqual(packages, [1, 2, 3])


class AddPackageMetadataTestCase(TestCase):
    def test(self) -> None:
        now = dt.datetime.now(tz=dt.UTC)
        build = BuildFactory(machine="babette")
        cache = QuickCache()

        for cpv in ["dev-vcs/git-2.34.1", "app-portage/gentoolkit-0.5.1-r1"]:
            self.artifact_builder.build(build, cpv)

        self.publisher.pull(build)
        record = self.publisher.record(build)
        context = cast(
            DashboardContext,
            {
                "now": now,
                "package_count": 0,
                "recent_packages": {"dev-vcs/git-2.34.1": {"gbp"}},
                "total_package_size_per_machine": {"babette": 0},
            },
        )
        new_context = add_package_metadata(record, context, self.publisher, cache)

        expected = {
            "now": now,
            "package_count": 6,
            "recent_packages": {
                "dev-vcs/git-2.34.1": {"babette", "gbp"},
                "app-portage/gentoolkit-0.5.1-r1": {"babette"},
            },
            "total_package_size_per_machine": {"babette": 3238},
        }

        self.assertEqual(new_context, expected)

    def test_when_record_not_completed(self) -> None:
        now = dt.datetime.now(tz=dt.UTC)
        build = BuildFactory(machine="babette")
        cache = QuickCache()

        record = self.publisher.record(build)
        context = cast(
            DashboardContext,
            {
                "now": now,
                "package_count": 0,
                "recent_packages": {},
                "total_package_size_per_machine": {"babette": 0},
            },
        )
        new_context = add_package_metadata(record, context, self.publisher, cache)

        expected = {
            "now": now,
            "package_count": 0,
            "recent_packages": {},
            "total_package_size_per_machine": {"babette": 0},
        }

        self.assertEqual(new_context, expected)


class GetBuildSummaryTestCase(TestCase):
    def test(self) -> None:
        now = dt.datetime.now(tz=dt.UTC)
        machines = ["babette", "lighthouse", "web"]
        cache = QuickCache()
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

        result = get_build_summary(now, machine_info, self.publisher, cache)

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


class GetMetadataTestCase(TestCase):
    """This is just cached Storage.get_metadata()"""

    def test(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        self.publisher.pull(build)

        metadata = get_metadata(build, self.publisher, cache)

        self.assertEqual(metadata, self.publisher.storage.get_metadata(build))
        self.assertEqual(cache.cache, {f"metadata-{build}": metadata})

    def test_when_cached_return_cache(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        cache.set(f"metadata-{build}", [1, 2, 3])  # not real metadata

        metadata = get_metadata(build, self.publisher, cache)

        self.assertEqual(metadata, [1, 2, 3])


class CreateDashboardContext(TestCase):
    """Tests for create_dashboard_context()"""

    maxDiff = None

    def test(self) -> None:
        start = dt.datetime.now(tz=dt.UTC)
        days = 2
        color_range = (Color(255, 0, 0), Color(0, 0, 255))
        publisher = self.publisher
        cache = QuickCache()

        lighthouse1 = BuildFactory(machine="lighthouse")
        for cpv in ["dev-vcs/git-2.34.1", "app-portage/gentoolkit-0.5.1-r1"]:
            self.artifact_builder.build(lighthouse1, cpv)
        publisher.pull(lighthouse1)

        polaris1 = BuildFactory(machine="polaris")
        publisher.publish(polaris1)
        polaris2 = BuildFactory(machine="polaris")
        publisher.pull(polaris2)

        polaris3 = BuildRecordFactory(machine="polaris")
        publisher.records.save(polaris3)

        input_context = ViewInputContext(
            cache=cache,
            color_range=color_range,
            days=days,
            now=start,
            publisher=publisher,
        )
        cxt = create_dashboard_context(input_context)
        self.assertEqual(len(cxt["chart_days"]), 2)
        self.assertEqual(cxt["build_count"], 4)
        self.assertEqual(
            cxt["build_packages"],
            {
                str(lighthouse1): [
                    "app-portage/gentoolkit-0.5.1-r1",
                    "dev-vcs/git-2.34.1",
                ],
                str(polaris2): [],
            },
        )
        self.assertEqual(cxt["gradient_colors"], ["#ff0000", "#0000ff"])
        self.assertEqual(cxt["builds_per_machine"], [3, 1])
        self.assertEqual(cxt["machines"], ["polaris", "lighthouse"])
        self.assertEqual(cxt["now"], start)
        self.assertEqual(cxt["package_count"], 14)
        self.assertEqual(cxt["unpublished_builds_count"], 2)
        self.assertEqual(
            cxt["recent_packages"],
            {
                "app-portage/gentoolkit-0.5.1-r1": {"lighthouse"},
                "dev-vcs/git-2.34.1": {"lighthouse"},
            },
        )


class GetQueryValueFromRequestTests(TestCase):
    def test_returns_fallback(self) -> None:
        request = mock.Mock(GET={})
        chart_days = get_query_value_from_request(request, "chart_days", int, 10)

        self.assertEqual(chart_days, 10)

    def test_with_queryparam(self) -> None:
        request = mock.Mock(GET={"chart_days": "10"})
        chart_days = get_query_value_from_request(request, "chart_days", int, 7)

        self.assertEqual(chart_days, 10)

    def test_with_invalid_queryparam(self) -> None:
        request = mock.Mock(GET={"chart_days": "bogus"})
        chart_days = get_query_value_from_request(request, "chart_days", int, 10)

        self.assertEqual(chart_days, 10)


class GetMachinesRecentPackagesTests(TestCase):
    def create_builds_and_packages(
        self, machine: str, number_of_builds: int, pkgs_per_build: int
    ) -> list[Build]:
        builds: list[Build] = BuildFactory.build_batch(
            number_of_builds, machine=machine
        )
        pf = package_factory()

        for build in builds:
            for _ in range(pkgs_per_build):
                package = next(pf)
                self.artifact_builder.build(build, package)

        return builds

    def test(self) -> None:
        builds = self.create_builds_and_packages("babette", 3, 4)
        for build in builds:
            self.publisher.pull(build)

        machine_info = MachineInfo("babette")

        recent_packages = get_machine_recent_packages(
            machine_info, self.publisher, QuickCache(), max_count=11
        )
        self.assertEqual(len(recent_packages), 11)

        pkgs_sorted = sorted(
            recent_packages, key=lambda pkg: pkg.build_time, reverse=True
        )
        self.assertEqual(recent_packages, pkgs_sorted)

    def test_no_builds(self) -> None:
        machine_info = MachineInfo("babette")
        recent_packages = get_machine_recent_packages(
            machine_info, self.publisher, QuickCache()
        )
        self.assertEqual(len(recent_packages), 0)

    def test_build_not_pulled(self) -> None:
        [build] = self.create_builds_and_packages("babette", 1, 4)
        publisher = self.publisher
        publisher.record(build).save(publisher.records)
        machine_info = MachineInfo("babette")

        recent_packages = get_machine_recent_packages(
            machine_info, self.publisher, QuickCache()
        )
        self.assertEqual(len(recent_packages), 0)
