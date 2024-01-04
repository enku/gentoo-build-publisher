"""Tests for custom template tags"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from unittest import TestCase

from django.template import TemplateSyntaxError
from django.template.loader import get_template

from gentoo_build_publisher.templatetags.gbp import circle, numberize


class NumberizeTestCase(TestCase):
    def test_should_return_whole_number_when_precision_0(self) -> None:
        value = 96_858_412

        result = numberize(value, 0)

        self.assertEqual(result, "96M")

    def test_number_less_than_1000(self) -> None:
        value = 968

        result = numberize(value, 2)

        self.assertEqual(result, "968")

    def test_number_less_than_1_000_000(self) -> None:
        value = 968_584

        result = numberize(value, 1)

        self.assertEqual(result, "968.5k")

    def test_number_less_than_1_000_000_000(self) -> None:
        value = 96_858_412

        result = numberize(value, 2)

        self.assertEqual(result, "96.85M")

    def test_number_greater_than_1_000_000_000(self) -> None:
        value = 6_123_000_548

        result = numberize(value, 2)

        self.assertEqual(result, "6.12G")

    def test_invalid_value(self) -> None:
        value = "this is not a number"

        with self.assertRaises(TemplateSyntaxError):
            numberize(value, 2)


class NumberedCircleTests(TestCase):
    maxDiff = None

    def test(self) -> None:
        expected = """\
<div class="col-lg-4" align="center">
  <svg class="bd-placeholder-img rounded-circle" width="140" height="140" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" focusable="false" role="img"><rect width="100%" height="100%" fill="#755245"/><text x="50%" y="50%" fill="#fff" dy=".3em" font-size="50px">452</text></svg>
  <h2>Builds</h2>
</div>
"""
        context = circle(452, "Builds", "#755245")
        template = get_template("gentoo_build_publisher/circle.html")
        result = template.render(context)
        self.assertEqual(result, expected)

    def test_large_number(self) -> None:
        expected = """\
<div class="col-lg-4" align="center">
  <svg class="bd-placeholder-img rounded-circle" width="140" height="140" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" focusable="false" role="img"><title>212351</title><rect width="100%" height="100%" fill="#755245"/><text x="50%" y="50%" fill="#fff" dy=".3em" font-size="50px">212k</text></svg>
  <h2>Packages</h2>
</div>
"""
        context = circle(212351, "Packages", "#755245")
        template = get_template("gentoo_build_publisher/circle.html")
        result = template.render(context)
        self.assertEqual(result, expected)
