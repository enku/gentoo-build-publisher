"""Tests for the dashboard utils"""

# pylint: disable=missing-docstring
import datetime as dt
from unittest import mock

from django.utils import timezone

from gentoo_build_publisher import publisher
from gentoo_build_publisher.common import Build, Content
from gentoo_build_publisher.utils.time import localtime
from gentoo_build_publisher.views.utils import (
    StatsCollector,
    get_metadata,
    get_query_value_from_request,
)

from . import QuickCache, TestCase
from .factories import ArtifactFactory, BuildFactory, package_factory


class GetMetadataTestCase(TestCase):
    """This is just cached Storage.get_metadata()"""

    def test(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        publisher.pull(build)

        metadata = get_metadata(build, cache)

        self.assertEqual(metadata, publisher.storage.get_metadata(build))
        self.assertEqual(cache.cache, {f"metadata-{build}": metadata})

    def test_when_cached_return_cache(self) -> None:
        build = BuildFactory()
        cache = QuickCache()
        cache.set(f"metadata-{build}", [1, 2, 3])  # not real metadata

        metadata = get_metadata(build, cache)

        self.assertEqual(metadata, [1, 2, 3])


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
        return StatsCollector(QuickCache())

    def test_init(self) -> None:
        publisher.pull(BuildFactory(machine="lighthouse"))
        publisher.pull(BuildFactory(machine="babette"))
        sc = self.stats_collector()

        self.assertEqual(sc.machines, ["babette", "lighthouse"])

    def test_package_count(self) -> None:
        for build in [
            *create_builds_and_packages("babette", 5, 2, self.artifact_builder),
            *create_builds_and_packages("lighthouse", 3, 4, self.artifact_builder),
        ]:
            publisher.pull(build)

        sc = self.stats_collector()

        # Each machine has an initial 4 packages. For babette each build adds 2
        # additional packages a total of 6 + 8 + 10 + 12 + 14 = 50. For lighthouse each
        # build adds 4 additional packages for a total of 8 + 12 + 16 = 36.
        self.assertEqual(sc.package_count("babette"), 50)
        self.assertEqual(sc.package_count("lighthouse"), 36)

    def test_build_packages(self) -> None:
        [build] = create_builds_and_packages("lighthouse", 1, 4, self.artifact_builder)
        publisher.pull(build)

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
            publisher.pull(build)
        assert build
        publisher.publish(build)

        sc = self.stats_collector()

        record = publisher.record(build)
        self.assertEqual(sc.latest_published("polaris"), record)
        self.assertEqual(sc.latest_published("babette"), None)
        self.assertEqual(sc.latest_published("lighthouse"), None)

    def test_recent_packages(self) -> None:
        for build in create_builds_and_packages("babette", 3, 4, self.artifact_builder):
            publisher.pull(build)

        sc = self.stats_collector()
        recent_packages = sc.recent_packages("babette", maximum=11)

        self.assertEqual(len(recent_packages), 11)

        pkgs_sorted = sorted(
            recent_packages, key=lambda pkg: pkg.build_time, reverse=True
        )
        self.assertEqual(recent_packages, pkgs_sorted)

    def test_total_package_size(self) -> None:
        for build in create_builds_and_packages("babette", 3, 4, self.artifact_builder):
            publisher.pull(build)

        sc = self.stats_collector()

        self.assertEqual(sc.total_package_size("babette"), 15941)
        self.assertEqual(sc.total_package_size("bogus"), 0)

    def test_latest_build(self) -> None:
        build = None
        for build in create_builds_and_packages("babette", 3, 4, self.artifact_builder):
            publisher.pull(build)
        assert build

        sc = self.stats_collector()

        self.assertEqual(sc.latest_build("babette"), publisher.record(build))
        self.assertEqual(sc.latest_build("bogus"), None)

    def test_built_recently(self) -> None:
        day = dt.timedelta(days=1)
        now = timezone.localtime()
        b1 = publisher.record(BuildFactory(machine="babette")).save(
            publisher.records, built=now - 2 * day
        )
        b2 = publisher.record(BuildFactory(machine="babette")).save(
            publisher.records, built=now - day
        )
        b3 = publisher.record(BuildFactory(machine="babette")).save(
            publisher.records, built=now
        )
        publisher.pull(b3)

        sc = self.stats_collector()

        self.assertFalse(sc.built_recently(b1, now))
        self.assertFalse(sc.built_recently(b2, now))
        self.assertTrue(sc.built_recently(b3, now))

    def test_builds_by_day(self) -> None:
        for hour in range(2):
            publisher.record(BuildFactory(machine="babette")).save(
                publisher.records,
                submitted=localtime(dt.datetime(2024, 1, 13, 12))
                + dt.timedelta(hours=hour),
            )
        for hour in range(3):
            publisher.record(BuildFactory(machine="babette")).save(
                publisher.records,
                submitted=localtime(dt.datetime(2024, 1, 14, 12))
                + dt.timedelta(hours=hour),
            )
        for hour in range(4):
            publisher.record(BuildFactory(machine="babette")).save(
                publisher.records,
                submitted=localtime(dt.datetime(2024, 1, 15, 12))
                + dt.timedelta(hours=hour),
            )

        bbd = self.stats_collector().builds_by_day("babette")
        expected = {
            dt.date(2024, 1, 13): 2,
            dt.date(2024, 1, 14): 3,
            dt.date(2024, 1, 15): 4,
        }
        self.assertEqual(bbd, expected)

    def test_packages_by_day(self) -> None:
        d1 = dt.datetime(2021, 4, 13, 9, 5)
        self.artifact_builder.timer = int(d1.timestamp())
        [build] = create_builds_and_packages("babette", 1, 3, self.artifact_builder)
        publisher.pull(build)
        gbp_json_path = publisher.storage.get_path(build, Content.BINPKGS) / "gbp.json"
        gbp_json_path.unlink()

        d2 = dt.datetime(2024, 1, 14, 9, 5)
        self.artifact_builder.timer = int(d2.timestamp())
        for build in create_builds_and_packages("babette", 2, 3, self.artifact_builder):
            publisher.pull(build)

        pbd = self.stats_collector().packages_by_day("babette")

        # d1's packages are skipped because there is on gbp.json
        self.assertEqual(list(pbd.keys()), [d2.date()])

        self.assertEqual(len(pbd[d2.date()]), 6)


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
