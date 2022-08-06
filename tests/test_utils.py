"""Tests for the gentoo_build_publisher.utils module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
from unittest import TestCase

from gentoo_build_publisher import utils


class ColorTestCase(TestCase):
    def test_str(self):
        color = utils.Color(255, 192, 203)

        color_str = str(color)

        self.assertEqual(color_str, "#ffc0cb")

    def test_gradient(self):
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

    def test_gradient_single_color(self):
        start = utils.Color(255, 192, 203)
        end = utils.Color(137, 207, 240)

        colors = utils.Color.gradient(start, end, 1)

        self.assertEqual(colors, [start])

    def test_gradient_0_colors_should_return_empty_list(self):
        start = utils.Color(255, 192, 203)
        end = utils.Color(137, 207, 240)

        colors = utils.Color.gradient(start, end, 0)

        self.assertEqual(colors, [])

    def test_gradient_2_colors_should_return_end_colors(self):
        start = utils.Color(255, 192, 203)
        end = utils.Color(137, 207, 240)

        colors = utils.Color.gradient(start, end, 2)

        self.assertEqual(colors, [start, end])


class LapsedTestCase(TestCase):
    def test(self):
        start = dt.datetime(2021, 11, 7, 9, 27, 0)
        end = dt.datetime(2021, 11, 7, 10, 28, 1)

        lapsed = utils.lapsed(start, end)

        self.assertEqual(lapsed, 3661)


class CPVToPathTestCase(TestCase):
    def test(self):
        cpv = "app-vim/gentoo-syntax-1"
        path = utils.cpv_to_path(cpv)

        self.assertEqual("app-vim/gentoo-syntax/gentoo-syntax-1-1.xpak", path)

    def test_raises_valueerror_when_not_valid_cpv(self):
        with self.assertRaises(ValueError):
            utils.cpv_to_path("foo-bar-1.0")
