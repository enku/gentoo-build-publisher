"""Unit tests for the purge module"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
import random
import typing as t
from dataclasses import dataclass
from unittest import TestCase

from unittest_fixtures import Fixtures, fixture, given

from gentoo_build_publisher.purge import Purger

# Random dates for testing
DATES = [
    "2015-12-31",
    "2015-12-30",
    "2016-01-01",
    "2016-05-11",
    "2017-10-10",
    "2018-03-27",
    "2018-04-21",
    "2020-01-14",
    "2020-02-06",
    "2020-02-14",
    "2020-07-29",
    "2020-09-29",
    "2020-10-19",
    "2020-12-25",
    "2020-12-31",
    "2020-12-31",
    "2021-03-01",
    "2021-03-09",
    "2021-03-25",
    "2021-03-17",
    "2021-03-27",
    "2021-03-27",
    "2021-04-01",
    "2021-04-05",
    "2021-04-12",
    "2021-04-12",
    "2021-04-13",
    "2021-04-14",
    "2021-04-16",
    "2021-04-17",
    "2021-04-20",
    "2021-04-20",
    "2021-04-20",
    "2021-04-21",
    "2021-04-21",
    "2021-04-21",
    "2024-04-21",  ## future
]

START = datetime.datetime(2016, 1, 1, 0, 0, 0)
END = datetime.datetime(2021, 4, 21)


@dataclass(frozen=True)
class Item:
    """Arbitrary item for testing"""

    timestamp: datetime.datetime

    def __eq__(self, other: t.Any) -> bool:
        return self is other

    def __hash__(self) -> int:
        return hash(self.timestamp)


def str2dt(string: str) -> datetime.datetime:
    year, month, day = [int(i) for i in string.split("-")]

    return datetime.datetime(year, month, day)


def items_fixture(_options: t.Any, _fixtures: Fixtures) -> list[Item]:
    dates = [*DATES]
    random.shuffle(dates)

    return [Item(timestamp=str2dt(i)) for i in dates]


@fixture(items_fixture)
def purger_fixture(_options: t.Any, fixtures: Fixtures) -> Purger[Item]:

    return Purger(fixtures.items, key=lambda i: i.timestamp, start=START, end=END)


# pylint: disable=unused-argument
@given(items_fixture, purger_fixture)
class PurgeTestCase(TestCase):
    def assertDates(self, items, expected) -> None:
        # pylint: disable=invalid-name
        item_dates = [
            datetime.datetime.strftime(i.timestamp, "%Y-%m-%d") for i in items
        ]

        self.assertEqual(set(item_dates), set(expected))

    def test_last_day_of_month(self, fixtures: Fixtures) -> None:
        self.assertEqual(
            fixtures.purger.last_day_of_month(END),
            datetime.datetime(2021, 4, 30, 23, 59, 59),
        )

    def test_yesterday_plus(self, fixtures: Fixtures) -> None:
        items = fixtures.purger.yesterday_plus()

        expected = [
            "2021-04-20",
            "2021-04-20",
            "2021-04-20",
            "2021-04-21",
            "2021-04-21",
            "2021-04-21",
            "2024-04-21",
        ]
        self.assertDates(items, expected)

    def test_one_per_day_last_week(self, fixtures: Fixtures) -> None:
        items = fixtures.purger.one_per_day_last_week()

        expected = ["2021-04-14", "2021-04-16", "2021-04-17", "2021-04-20"]
        self.assertDates(items, expected)

    def test_one_per_week_last_month(self, fixtures: Fixtures) -> None:
        items = fixtures.purger.one_per_week_last_month()

        expected = ["2021-03-01", "2021-03-09", "2021-03-17", "2021-03-27"]

        self.assertDates(items, expected)

    def test_one_per_month_last_year(self, fixtures: Fixtures) -> None:
        items = fixtures.purger.one_per_month_last_year()

        expected = [
            "2020-07-29",
            "2020-09-29",
            "2020-10-19",
            "2020-12-31",
            "2021-03-27",
            "2021-04-21",
        ]

        self.assertDates(items, expected)

    def test_one_per_year(self, fixtures: Fixtures) -> None:
        items = fixtures.purger.one_per_year()

        expected = [
            "2015-12-31",
            "2016-05-11",
            "2017-10-10",
            "2018-04-21",
            "2020-12-31",
            "2021-04-21",
            "2024-04-21",
        ]

        self.assertDates(items, expected)

    def test_past(self, fixtures: Fixtures) -> None:
        items = fixtures.purger.past()

        expected = ["2015-12-30", "2015-12-31"]

        self.assertDates(items, expected)

    def test_filter_range(self, fixtures: Fixtures) -> None:
        start = datetime.datetime(2017, 4, 21)
        end = datetime.datetime(2019, 12, 31)

        filtered = fixtures.purger.filter_range(fixtures.items, start, end)

        expected = {
            datetime.datetime(2017, 10, 10, 0, 0),
            datetime.datetime(2018, 3, 27, 0, 0),
            datetime.datetime(2018, 4, 21, 0, 0),
        }

        self.assertEqual(set(i.timestamp for i in filtered), expected)

    def test_purge(self, fixtures: Fixtures) -> None:
        to_purge = fixtures.purger.purge()

        expected = [
            "2016-01-01",
            "2018-03-27",
            "2020-01-14",
            "2020-02-06",
            "2020-02-14",
            "2020-12-25",
            "2021-03-25",
            "2021-03-27",
            "2021-04-01",
            "2021-04-05",
            "2021-04-12",
            "2021-04-13",
        ]

        self.assertDates(to_purge, expected)
