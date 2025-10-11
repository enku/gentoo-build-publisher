"""Tests for the stats module"""

# pylint: disable=missing-docstring

import datetime as dt
from unittest import TestCase

from django.utils import timezone
from unittest_fixtures import Fixtures, given

import gbp_testkit.fixtures as testkit
from gbp_testkit.factories import BuildFactory, BuildRecordFactory
from gentoo_build_publisher.cache import GBPSiteCache
from gentoo_build_publisher.cache import cache as site_cache
from gentoo_build_publisher.cache import clear as clear_cache
from gentoo_build_publisher.stats import Stats, StatsCollector
from gentoo_build_publisher.types import Content
from gentoo_build_publisher.utils.time import localtime

from .lib import create_builds_and_packages


@given(testkit.publisher)
@given(stats_collector=lambda _: StatsCollector())
class StatsCollectorTests(TestCase):
    def test_init(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        publisher.pull(BuildFactory(machine="lighthouse"))
        publisher.pull(BuildFactory(machine="babette"))
        sc = fixtures.stats_collector

        self.assertEqual(sc.machines, ["babette", "lighthouse"])

    def test_package_count(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        for build in [
            *create_builds_and_packages("babette", 5, 2, builder),
            *create_builds_and_packages("lighthouse", 3, 4, builder),
        ]:
            publisher.pull(build)

        sc = fixtures.stats_collector

        # Each machine has an initial 4 packages. For babette each build adds 2
        # additional packages a total of 6 + 8 + 10 + 12 + 14 = 50. For lighthouse each
        # build adds 4 additional packages for a total of 8 + 12 + 16 = 36.
        self.assertEqual(sc.package_count("babette"), 50)
        self.assertEqual(sc.package_count("lighthouse"), 36)

    def test_build_packages(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        [build] = create_builds_and_packages("lighthouse", 1, 4, builder)
        publisher.pull(build)

        sc = fixtures.stats_collector

        expected = [
            "dev-python/gcc-1.0",
            "dev-python/markdown-1.0",
            "dev-python/mesa-1.0",
            "dev-python/pycups-1.0",
        ]
        self.assertEqual(sc.build_packages(build), expected)

    def test_latest_published(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        build = None
        for build in [
            *create_builds_and_packages("babette", 5, 2, builder),
            *create_builds_and_packages("lighthouse", 3, 4, builder),
            *create_builds_and_packages("polaris", 3, 1, builder),
        ]:
            publisher.pull(build)
        assert build
        publisher.publish(build)

        sc = fixtures.stats_collector

        record = publisher.record(build)
        self.assertEqual(sc.latest_published("polaris"), record)
        self.assertEqual(sc.latest_published("babette"), None)
        self.assertEqual(sc.latest_published("lighthouse"), None)

    def test_recent_packages(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        for build in create_builds_and_packages("babette", 3, 4, builder):
            publisher.pull(build)

        sc = fixtures.stats_collector
        recent_packages = sc.recent_packages("babette", maximum=11)

        self.assertEqual(len(recent_packages), 11)

        pkgs_sorted = sorted(
            recent_packages, key=lambda pkg: pkg.build_time, reverse=True
        )
        self.assertEqual(recent_packages, pkgs_sorted)

    def test_total_package_size(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        for build in create_builds_and_packages("babette", 3, 4, builder):
            publisher.pull(build)

        sc = fixtures.stats_collector

        self.assertEqual(sc.total_package_size("babette"), 15941)
        self.assertEqual(sc.total_package_size("bogus"), 0)

    def test_latest_build(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        build = None
        for build in create_builds_and_packages("babette", 3, 4, builder):
            publisher.pull(build)
        assert build

        sc = fixtures.stats_collector

        self.assertEqual(sc.latest_build("babette"), publisher.record(build))
        self.assertEqual(sc.latest_build("bogus"), None)

    def test_built_recently(self, fixtures: Fixtures) -> None:
        day = dt.timedelta(days=1)
        now = timezone.localtime()
        publisher = fixtures.publisher
        b1 = publisher.save(BuildRecordFactory(machine="babette"))
        b2 = publisher.save(BuildRecordFactory(machine="babette"), built=now - day)
        b3 = publisher.save(BuildRecordFactory(machine="babette"), built=now)
        publisher.pull(b3)

        sc = fixtures.stats_collector

        self.assertFalse(sc.built_recently(b1, now))
        self.assertFalse(sc.built_recently(b2, now))
        self.assertTrue(sc.built_recently(b3, now))

    def test_builds_by_day(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        for hour in range(2):
            publisher.save(
                BuildRecordFactory(machine="babette"),
                submitted=localtime(dt.datetime(2024, 1, 13, 12))
                + dt.timedelta(hours=hour),
            )
        for hour in range(3):
            publisher.save(
                BuildRecordFactory(machine="babette"),
                submitted=localtime(dt.datetime(2024, 1, 14, 12))
                + dt.timedelta(hours=hour),
            )
        for hour in range(4):
            publisher.save(
                BuildRecordFactory(machine="babette"),
                submitted=localtime(dt.datetime(2024, 1, 15, 12))
                + dt.timedelta(hours=hour),
            )

        bbd = fixtures.stats_collector.builds_by_day("babette")
        expected = {
            dt.date(2024, 1, 13): 2,
            dt.date(2024, 1, 14): 3,
            dt.date(2024, 1, 15): 4,
        }
        self.assertEqual(bbd, expected)

    def test_packages_by_day(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        d1 = dt.datetime(2021, 4, 13, 9, 5)
        builder.timer = int(d1.timestamp())
        [build] = create_builds_and_packages("babette", 1, 3, builder)
        publisher.pull(build)
        gbp_json_path = publisher.storage.get_path(build, Content.BINPKGS) / "gbp.json"
        gbp_json_path.unlink()

        d2 = dt.datetime(2024, 1, 14, 9, 5)
        builder.timer = int(d2.timestamp())

        [build] = create_builds_and_packages("babette", 1, 3, builder)
        publisher.pull(build)
        [build] = create_builds_and_packages("babette", 1, 3, builder)
        publisher.pull(build)

        pbd = fixtures.stats_collector.packages_by_day("babette")

        self.assertEqual(list(pbd.keys()), [d2.date(), d1.date()])

        self.assertEqual(len(pbd[d2.date()]), 6)


@given(testkit.publisher)
class StatsTests(TestCase):
    # pylint: disable=unused-argument
    def test_collect(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        for build in [
            *create_builds_and_packages("babette", 5, 2, builder),
            *create_builds_and_packages("lighthouse", 3, 4, builder),
        ]:
            publisher.pull(build)
        clear_cache(site_cache)

        stats = Stats.collect()

        self.assertEqual(stats.machines, ["babette", "lighthouse"])
        self.assertEqual(stats.package_counts, {"babette": 50, "lighthouse": 36})
        self.assertEqual(
            stats.total_package_size, {"babette": 22554, "lighthouse": 15941}
        )

    def test_with_cache_creates_cache_entry(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        for build in [
            *create_builds_and_packages("babette", 5, 2, builder),
            *create_builds_and_packages("lighthouse", 3, 4, builder),
        ]:
            publisher.pull(build)
            # because of signals this should populate the cache

        cache = GBPSiteCache("test_with_cache_creates_cache_entry-")
        stats = Stats.with_cache(cache)

        self.assertEqual(stats.machines, ["babette", "lighthouse"])
        self.assertEqual(stats.package_counts, {"babette": 50, "lighthouse": 36})
        self.assertEqual(
            stats.total_package_size, {"babette": 22554, "lighthouse": 15941}
        )

    def test_with_cache_and_exists_in_cache(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache("test_with_cache_and_exists_in_cache-")
        stats = Stats.collect()
        cache.test = stats

        with_cache = Stats.with_cache(cache)

        self.assertEqual(stats, with_cache)
