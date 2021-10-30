"""Tests for custom template tags"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from unittest import TestCase

from django.template import TemplateSyntaxError

from gentoo_build_publisher.templatetags.gbp import numberize


class NumberizeTestCase(TestCase):
    def test_should_return_whole_number_when_precision_0(self):
        value = 96_858_412

        result = numberize(value, 0)

        self.assertEqual(result, "96M")

    def test_number_less_than_1000(self):
        value = 968

        result = numberize(value, 2)

        self.assertEqual(result, "968")

    def test_number_less_than_1_000_000(self):
        value = 968_584

        result = numberize(value, 1)

        self.assertEqual(result, "968.5k")

    def test_number_less_than_1_000_000_000(self):
        value = 96_858_412

        result = numberize(value, 2)

        self.assertEqual(result, "96.85M")

    def test_number_greater_than_1_000_000_000(self):
        value = 6_123_000_548

        result = numberize(value, 2)

        self.assertEqual(result, "6.12G")

    def test_invalid_value(self):
        value = "this is not a number"

        with self.assertRaises(TemplateSyntaxError):
            numberize(value, 2)
