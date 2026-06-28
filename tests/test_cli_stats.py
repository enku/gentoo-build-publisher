"""Tests for the `gbp stats` cli subcommand"""

# pylint: disable=missing-docstring

from unittest_fixtures import Fixtures, given

import gbp_testkit.fixtures as testkit
from gbp_testkit import DjangoTestCase
from gentoo_build_publisher.cache import cache
from gentoo_build_publisher.stats import Stats


@given(testkit.gbpcli)
@given(cleared_stats=lambda _: cache.delete("stats"))
class TestCase(DjangoTestCase):
    """Base TestCase"""

    # pylint: disable=unused-argument
    def test_starts_with_cleared_stats(self, fixtures: Fixtures) -> None:
        self.assertIsNone(cache.get("stats"))


@given()
class GBPStatsClearTests(TestCase):
    """Tests for `gbp stats clear`"""

    def test_clears_stats(self, fixtures: Fixtures) -> None:
        cli = fixtures.gbpcli
        Stats.with_cache()

        self.assertIsNotNone(cache.get("stats"))

        status = cli("gbp stats clear")

        self.assertEqual(status, 0)
        self.assertIsNone(cache.get("stats"))

    def test_clear_when_no_stats(self, fixtures: Fixtures) -> None:
        cli = fixtures.gbpcli

        self.assertIsNone(cache.get("stats"))

        status = cli("gbp stats clear")

        self.assertEqual(status, 0)
        self.assertIsNone(cache.get("stats"))


@given()
class GBPStatsCollectTests(TestCase):
    """Tests for `gbp stats collect`"""

    def test_collects_stats(self, fixtures: Fixtures) -> None:
        cli = fixtures.gbpcli

        status = cli("gbp stats collect")

        self.assertEqual(status, 0)
        self.assertIsNotNone(cache.get("stats"))


@given()
class GBPStatsDumpTests(TestCase):
    """Tests for `gbp stats dump`"""

    def test_prints_stats_when_cached(self, fixtures: Fixtures) -> None:
        cli = fixtures.gbpcli
        console = fixtures.console
        Stats.with_cache()

        status = cli("gbp stats dump")

        self.assertEqual(status, 0)
        expected = """\
Stats(
    machines=[],
    machine_info={},
    package_counts={},
    build_packages={},
    latest_build={},
    latest_published={},
    recent_packages={},
    total_package_size={},
    builds_by_day={},
    packages_by_day={}
)
"""
        self.assertEqual(console.stdout, f"$ gbp stats dump\n{expected}")
