"""Tests for the dashboard utils"""
# pylint: disable=missing-docstring
import datetime as dt
from typing import cast
from unittest import mock

from gentoo_build_publisher.common import Content
from gentoo_build_publisher.publisher import MachineInfo
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.views import (
    DashboardContext,
    ViewInputContext,
    add_package_metadata,
    bot_to_list,
    create_dashboard_context,
    get_build_summary,
    get_metadata,
    get_packages,
    get_query_value_from_request,
)

from . import QuickCache, TestCase
from .factories import BuildFactory, BuildRecordFactory


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
                "total_package_size": {"babette": 0},
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
            "total_package_size": {"babette": 3238},
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
                "total_package_size": {"babette": 0},
            },
        )
        new_context = add_package_metadata(record, context, self.publisher, cache)

        expected = {
            "now": now,
            "package_count": 0,
            "recent_packages": {},
            "total_package_size": {"babette": 0},
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


class BOTToListTestCase(TestCase):
    """Tests for the bot_to_list function"""

    def test(self) -> None:
        bot = {
            dt.date(2023, 1, 24): {"polaris": 4, "babette": 0},
            dt.date(2023, 1, 25): {"polaris": 0, "babette": 4},
            dt.date(2023, 1, 26): {"polaris": 4, "babette": 4},
        }

        lst = bot_to_list(bot)

        self.assertEqual(lst, [[4, 0, 4], [0, 4, 4]])

    def test_when_empty(self) -> None:
        lst = bot_to_list({})

        self.assertEqual(lst, [])


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
        self.assertEqual(len(cxt["bot_days"]), 2)
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
        self.assertEqual(cxt["machine_dist"], [3, 1])
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
        bot_days = get_query_value_from_request(request, "bot_days", int, 10)

        self.assertEqual(bot_days, 10)

    def test_with_queryparam(self) -> None:
        request = mock.Mock(GET={"bot_days": "10"})
        bot_days = get_query_value_from_request(request, "bot_days", int, 7)

        self.assertEqual(bot_days, 10)

    def test_with_invalid_queryparam(self) -> None:
        request = mock.Mock(GET={"bot_days": "bogus"})
        bot_days = get_query_value_from_request(request, "bot_days", int, 10)

        self.assertEqual(bot_days, 10)
