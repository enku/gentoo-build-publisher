"""Tests for the gentoo_build_publisher.utils module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
import typing as t
from unittest import TestCase, mock

from gentoo_build_publisher import utils


class ColorTestCase(TestCase):
    def test_str(self) -> None:
        color = utils.Color(255, 192, 203)

        color_str = str(color)

        self.assertEqual(color_str, "#ffc0cb")

    def test_gradient(self) -> None:
        start = utils.Color(255, 192, 203)
        end = utils.Color(137, 207, 240)

        expected = [
            start,
            utils.Color(red=225, green=195, blue=212),
            utils.Color(red=196, green=199, blue=221),
            utils.Color(red=166, green=203, blue=230),
            end,
        ]

        colors = utils.Color.gradient(start, end, 5)

        self.assertEqual(colors, expected)

    def test_gradient_single_color(self) -> None:
        start = utils.Color(255, 192, 203)
        end = utils.Color(137, 207, 240)

        colors = utils.Color.gradient(start, end, 1)

        self.assertEqual(colors, [start])

    def test_gradient_0_colors_should_return_empty_list(self) -> None:
        start = utils.Color(255, 192, 203)
        end = utils.Color(137, 207, 240)

        colors = utils.Color.gradient(start, end, 0)

        self.assertEqual(colors, [])

    def test_gradient_2_colors_should_return_end_colors(self) -> None:
        start = utils.Color(255, 192, 203)
        end = utils.Color(137, 207, 240)

        colors = utils.Color.gradient(start, end, 2)

        self.assertEqual(colors, [start, end])


class LapsedTestCase(TestCase):
    def test(self) -> None:
        start = dt.datetime(2021, 11, 7, 9, 27, 0)
        end = dt.datetime(2021, 11, 7, 10, 28, 1)

        lapsed = utils.lapsed(start, end)

        self.assertEqual(lapsed, 3661)


class CPVToPathTestCase(TestCase):
    def test(self) -> None:
        cpv = "app-vim/gentoo-syntax-1"
        path = utils.cpv_to_path(cpv)

        self.assertEqual("app-vim/gentoo-syntax/gentoo-syntax-1-1.xpak", path)

    def test_raises_valueerror_when_not_valid_cpv(self) -> None:
        with self.assertRaises(ValueError):
            utils.cpv_to_path("foo-bar-1.0")


class CheckTagNameTestCase(TestCase):
    def test_empty_string_is_a_valid_tag(self) -> None:
        utils.check_tag_name("")

    def test_tag_names_cannot_start_with_a_dash(self) -> None:
        with self.assertRaises(utils.InvalidTagName):
            utils.check_tag_name("-prod")

    def test_tag_names_cannot_start_with_a_dot(self) -> None:
        with self.assertRaises(utils.InvalidTagName):
            utils.check_tag_name(".prod")

    def test_tag_names_cannot_be_more_than_128_chars(self) -> None:
        tag_name = "a" * 129

        with self.assertRaises(utils.InvalidTagName):
            utils.check_tag_name(tag_name)

    def test_tag_name_cannot_have_non_ascii_chars(self) -> None:
        with self.assertRaises(utils.InvalidTagName):
            utils.check_tag_name("pròd")


class UtcTime(TestCase):
    """Tests for utils.utctime"""

    def test_should_give_the_time_with_utc_timezone(self) -> None:
        time = dt.datetime(2022, 9, 17, 17, 36)

        result = utils.utctime(time)

        self.assertEqual(result, time.replace(tzinfo=dt.timezone.utc))

    @mock.patch("gentoo_build_publisher.utils.dt.datetime")
    def test_time_defaults_to_now(self, datetime: mock.Mock) -> None:
        datetime.utcnow.return_value = utcnow = dt.datetime(2022, 9, 17, 17, 36)

        result = utils.utctime()

        self.assertEqual(result, utcnow.replace(tzinfo=dt.timezone.utc))


class GetNext(TestCase):
    def test_with_next(self) -> None:
        myiter: t.Iterator[int] = iter([1, 2, 3])
        next(myiter)

        self.assertEqual(utils.get_next(myiter), 2)

    def test_with_exhausted_iterable(self) -> None:
        myiter: t.Iterator[int] = iter([])

        self.assertEqual(utils.get_next(myiter), None)
