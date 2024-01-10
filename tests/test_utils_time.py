# pylint: disable=missing-docstring
import datetime as dt
from unittest import TestCase, mock

from gentoo_build_publisher.utils import time


class UtcTime(TestCase):
    """Tests for utils.utctime"""

    def test_should_give_the_time_with_utc_timezone(self) -> None:
        timestamp = dt.datetime(2022, 9, 17, 17, 36)

        result = time.utctime(timestamp)

        self.assertEqual(result, timestamp.replace(tzinfo=dt.timezone.utc))

    @mock.patch("gentoo_build_publisher.utils.time.dt.datetime")
    def test_time_defaults_to_now(self, datetime: mock.Mock) -> None:
        datetime.utcnow.return_value = utcnow = dt.datetime(2022, 9, 17, 17, 36)

        result = time.utctime()

        self.assertEqual(result, utcnow.replace(tzinfo=dt.timezone.utc))


class LapsedTestCase(TestCase):
    def test(self) -> None:
        start = dt.datetime(2021, 11, 7, 9, 27, 0)
        end = dt.datetime(2021, 11, 7, 10, 28, 1)

        lapsed = time.lapsed(start, end)

        self.assertEqual(lapsed, 3661)
