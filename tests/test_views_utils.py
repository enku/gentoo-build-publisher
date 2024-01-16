"""Tests for the dashboard utils"""
# pylint: disable=missing-docstring
import datetime as dt
from unittest import mock

from django.utils import timezone

from gentoo_build_publisher.common import Build
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.views import (
    StatsCollector,
    ViewInputContext,
    create_dashboard_context,
    get_metadata,
    get_query_value_from_request,
)

from . import QuickCache, TestCase
from .factories import (
    ArtifactFactory,
    BuildFactory,
    BuildRecordFactory,
    package_factory,
)


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

    def input_context(self) -> ViewInputContext:
        return ViewInputContext(
            cache=QuickCache(),
            color_range=(Color(255, 0, 0), Color(0, 0, 255)),
            days=2,
            now=timezone.localtime(),
            publisher=self.publisher,
        )

    def test(self) -> None:
        publisher = self.publisher
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

        input_context = self.input_context()
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
        self.assertEqual(cxt["now"], input_context.now)
        self.assertEqual(cxt["package_count"], 14)
        self.assertEqual(cxt["unpublished_builds_count"], 2)
        self.assertEqual(
            cxt["total_package_size_per_machine"], {"lighthouse": 3238, "polaris": 3906}
        )
        self.assertEqual(
            cxt["recent_packages"],
            {
                "app-portage/gentoolkit-0.5.1-r1": {"lighthouse"},
                "dev-vcs/git-2.34.1": {"lighthouse"},
            },
        )

    def test_not_completed(self) -> None:
        publisher = self.publisher

        publisher.pull(BuildFactory())
        build = BuildFactory()
        record = publisher.record(build).save(publisher.records, completed=None)

        cxt = create_dashboard_context(self.input_context())
        self.assertEqual(cxt["builds_not_completed"], [record])

    def test_latest_published(self) -> None:
        babette = BuildFactory(machine="babette")
        self.publisher.publish(babette)
        self.publisher.pull(BuildFactory(machine="lighthouse"))
        self.publisher.pull(BuildFactory(machine="polaris"))

        cxt = create_dashboard_context(self.input_context())
        self.assertEqual(cxt["latest_published"], set([self.publisher.record(babette)]))
        self.assertEqual(cxt["unpublished_builds_count"], 2)

    def test_builds_over_time_and_build_recently(self) -> None:
        now = timezone.localtime()
        for machine in ["babette", "lighthouse"]:
            for day in range(2):
                for _ in range(3):
                    build = BuildFactory(machine=machine)
                    record = self.publisher.record(build)
                    record = record.save(
                        self.publisher.records, submitted=now - dt.timedelta(days=day)
                    )
                    self.publisher.pull(record)
                    if day == 0:
                        break

        cxt = create_dashboard_context(self.input_context())
        self.assertEqual(cxt["builds_over_time"], [[3, 1], [3, 1]])
        self.assertEqual(len(cxt["built_recently"]), 2)


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


class StatsCollectorTests(TestCase):
    def stats_collector(self) -> StatsCollector:
        return StatsCollector(self.publisher, QuickCache())

    def test_init(self) -> None:
        self.publisher.pull(BuildFactory(machine="lighthouse"))
        self.publisher.pull(BuildFactory(machine="babette"))
        sc = self.stats_collector()

        self.assertEqual(sc.machines, ["babette", "lighthouse"])

    def test_package_count(self) -> None:
        for build in [
            *create_builds_and_packages("babette", 5, 2, self.artifact_builder),
            *create_builds_and_packages("lighthouse", 3, 4, self.artifact_builder),
        ]:
            self.publisher.pull(build)

        sc = self.stats_collector()

        # Each machine has an initial 4 packages. For babette each build adds 2
        # additional packages a total of 6 + 8 + 10 + 12 + 14 = 50. For lighthouse each
        # build adds 4 additional packages for a total of 8 + 12 + 16 = 36.
        self.assertEqual(sc.package_count("babette"), 50)
        self.assertEqual(sc.package_count("lighthouse"), 36)

    def test_build_packages(self) -> None:
        [build] = create_builds_and_packages("lighthouse", 1, 4, self.artifact_builder)
        self.publisher.pull(build)

        sc = self.stats_collector()

        expected = [
            "dev-python/gcc-1.0",
            "dev-python/markdown-1.0",
            "dev-python/mesa-1.0",
            "dev-python/pycups-1.0",
        ]
        self.assertEqual(sc.build_packages(build), expected)

    def test_latest_published(self) -> None:
        build = None
        for build in [
            *create_builds_and_packages("babette", 5, 2, self.artifact_builder),
            *create_builds_and_packages("lighthouse", 3, 4, self.artifact_builder),
            *create_builds_and_packages("polaris", 3, 1, self.artifact_builder),
        ]:
            self.publisher.pull(build)
        assert build
        self.publisher.publish(build)

        sc = self.stats_collector()

        record = self.publisher.record(build)
        self.assertEqual(sc.latest_published("polaris"), record)
        self.assertEqual(sc.latest_published("babette"), None)
        self.assertEqual(sc.latest_published("lighthouse"), None)

    def test_recent_packages(self) -> None:
        for build in create_builds_and_packages("babette", 3, 4, self.artifact_builder):
            self.publisher.pull(build)

        sc = self.stats_collector()
        recent_packages = sc.recent_packages("babette", maximum=11)

        self.assertEqual(len(recent_packages), 11)

        pkgs_sorted = sorted(
            recent_packages, key=lambda pkg: pkg.build_time, reverse=True
        )
        self.assertEqual(recent_packages, pkgs_sorted)

    def test_total_package_size(self) -> None:
        for build in create_builds_and_packages("babette", 3, 4, self.artifact_builder):
            self.publisher.pull(build)

        sc = self.stats_collector()

        self.assertEqual(sc.total_package_size("babette"), 15941)
        self.assertEqual(sc.total_package_size("bogus"), 0)

    def test_latest_build(self) -> None:
        build = None
        for build in create_builds_and_packages("babette", 3, 4, self.artifact_builder):
            self.publisher.pull(build)
        assert build

        sc = self.stats_collector()

        self.assertEqual(sc.latest_build("babette"), self.publisher.record(build))
        self.assertEqual(sc.latest_build("bogus"), None)

    def test_built_recently(self) -> None:
        day = dt.timedelta(days=1)
        now = timezone.localtime()
        b1 = self.publisher.record(BuildFactory(machine="babette")).save(
            self.publisher.records, built=now - 2 * day
        )
        b2 = self.publisher.record(BuildFactory(machine="babette")).save(
            self.publisher.records, built=now - day
        )
        b3 = self.publisher.record(BuildFactory(machine="babette")).save(
            self.publisher.records, built=now
        )
        self.publisher.pull(b3)

        sc = self.stats_collector()

        self.assertFalse(sc.built_recently(b1, now))
        self.assertFalse(sc.built_recently(b2, now))
        self.assertTrue(sc.built_recently(b3, now))

    def test_builds_by_day(self) -> None:
        for hour in range(2):
            self.publisher.record(BuildFactory(machine="babette")).save(
                self.publisher.records,
                submitted=dt.datetime(2024, 1, 13, 12).astimezone()
                + dt.timedelta(hours=hour),
            )
        for hour in range(3):
            self.publisher.record(BuildFactory(machine="babette")).save(
                self.publisher.records,
                submitted=dt.datetime(2024, 1, 14, 12).astimezone()
                + dt.timedelta(hours=hour),
            )
        for hour in range(4):
            self.publisher.record(BuildFactory(machine="babette")).save(
                self.publisher.records,
                submitted=dt.datetime(2024, 1, 15, 12).astimezone()
                + dt.timedelta(hours=hour),
            )

        bbd = self.stats_collector().builds_by_day("babette")
        expected = {
            dt.date(2024, 1, 13): 2,
            dt.date(2024, 1, 14): 3,
            dt.date(2024, 1, 15): 4,
        }
        self.assertEqual(bbd, expected)


def create_builds_and_packages(
    machine: str,
    number_of_builds: int,
    pkgs_per_build: int,
    artifact_builder: ArtifactFactory,
) -> list[Build]:
    builds: list[Build] = BuildFactory.build_batch(number_of_builds, machine=machine)
    pf = package_factory()

    for build in builds:
        for _ in range(pkgs_per_build):
            package = next(pf)
            artifact_builder.build(build, package)

    return builds
