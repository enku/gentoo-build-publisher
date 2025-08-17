"""Tests for the gentoo_build_publisher.utils module"""

# pylint: disable=missing-docstring,unused-argument
import datetime as dt
from unittest import TestCase
from zoneinfo import ZoneInfo

from unittest_fixtures import Fixtures, given, where

import gbp_testkit.fixtures as testkit
from gentoo_build_publisher.utils import time

CT = ZoneInfo("America/Chicago")
NOW = dt.datetime(2024, 1, 9, 21, 5, 5, tzinfo=CT)
YESTERDAY = dt.datetime(2024, 1, 8, 9, 0, 0, tzinfo=CT)
THREE_HOURS = dt.timedelta(hours=3)


@given(now=testkit.patch)
@where(now__target="gentoo_build_publisher.utils.time.now")
@where(now__return_value=dt.datetime(2022, 9, 17, 17, 36, tzinfo=dt.UTC))
class UtcTime(TestCase):
    """Tests for time.utctime"""

    def test_should_give_the_time_with_utc_timezone(self, fixtures: Fixtures) -> None:
        timestamp = dt.datetime(2022, 9, 17, 17, 36)

        result = time.utctime(timestamp)

        self.assertEqual(result, timestamp.replace(tzinfo=dt.UTC))

    def test_time_defaults_to_now(self, fixtures: Fixtures) -> None:
        result = time.utctime()

        self.assertEqual(result, fixtures.now().replace(tzinfo=dt.UTC))


class LapsedTestCase(TestCase):
    def test(self) -> None:
        start = dt.datetime(2021, 11, 7, 9, 27, 0)
        end = dt.datetime(2021, 11, 7, 10, 28, 1)

        lapsed = time.lapsed(start, end)

        self.assertEqual(lapsed, 3661)


class IsSameDayTests(TestCase):
    def test_true(self) -> None:
        first = NOW
        second = NOW - THREE_HOURS

        self.assertTrue(time.is_same_day(first, second))

    def test_false(self) -> None:
        first = NOW
        second = NOW + THREE_HOURS

        self.assertFalse(time.is_same_day(first, second))


class IsPreviousDayTests(TestCase):
    def test_true(self) -> None:
        self.assertTrue(time.is_previous_day(YESTERDAY, NOW))

    def test_false(self) -> None:
        self.assertFalse(time.is_previous_day(NOW, YESTERDAY))


class AsTimeTests(TestCase):
    def test(self) -> None:
        self.assertEqual(time.as_time(NOW), "21:05:05")
        self.assertEqual(time.as_time(NOW), "21:05:05")


class AsDateTests(TestCase):
    def test(self) -> None:
        self.assertEqual(time.as_date(NOW), "Jan 9")


class AsDateAndTimeTests(TestCase):
    def test(self) -> None:
        self.assertEqual(time.as_date_and_time(NOW), "Jan 9 21:05")
