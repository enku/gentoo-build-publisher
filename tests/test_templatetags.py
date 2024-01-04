"""Tests for custom template tags"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from unittest import TestCase

from django.template import TemplateSyntaxError
from django.template.loader import get_template

from gentoo_build_publisher.common import Build
from gentoo_build_publisher.templatetags.gbp import (
    build_row,
    chart,
    circle,
    numberize,
    package_row,
)


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


class ChartTests(TestCase):
    def test(self) -> None:
        expected = """\
<div class="col-md-8">
  <h4 class="d-flex justify-content-between align-items-center mb-3">Test Test</h4>
  <canvas id="testChart" width="100" height="150"></canvas>
</div>
"""
        context = chart("testChart", "Test Test", cols=8, width=100, height=150)
        template = get_template("gentoo_build_publisher/chart.html")
        result = template.render(context)
        self.assertEqual(result, expected)


class BuildRowTests(TestCase):
    def test(self) -> None:
        expected = """\
<li class="list-group-item d-flex justify-content-between lh-condensed">
  <div>
    <h6 class="my-0">babette</h6>
    <small class="text-muted">1094</small>
  </div>
  <span title="Packages" class="text-muted" data-bs-toggle="popover" data-bs-trigger="hover focus" data-bs-content='x11-libs/libdrm-2.4.118&lt;br/&gt;x11-misc/xkeyboard-config-2.40-r1' data-bs-html="true">2 packages</span>
</li>
"""
        build = Build("babette", "1094")
        packages = ["x11-libs/libdrm-2.4.118", "x11-misc/xkeyboard-config-2.40-r1"]
        build_packages = {"babette.1094": packages}
        context = build_row(build, build_packages)
        template = get_template("gentoo_build_publisher/build_row.html")
        result = template.render(context)
        self.assertEqual(result, expected)


class PackageRowTests(TestCase):
    def test(self) -> None:
        expected = """\
<li class="list-group-item d-flex justify-content-between lh-condensed">
  <div title="Machines" data-bs-toggle="popover" data-bs-trigger="hover focus" data-bs-content='babette&lt;br/&gt;polaris' data-bs-html="true">
    <h6 class="my-0">x11-libs/libdrm-2.4.118</h6>
    <small class="text-muted">2 machines</small>
  </div>
</li>
"""
        package = "x11-libs/libdrm-2.4.118"
        machines = ["babette", "polaris"]
        context = package_row(package, machines)
        template = get_template("gentoo_build_publisher/package_row.html")
        result = template.render(context)
        self.assertEqual(result, expected)

    def test_single_machine(self) -> None:
        expected = """\
<li class="list-group-item d-flex justify-content-between lh-condensed">
  <div title="Machines" data-bs-toggle="popover" data-bs-trigger="hover focus" data-bs-content='babette' data-bs-html="true">
    <h6 class="my-0">x11-libs/libdrm-2.4.118</h6>
    <small class="text-muted">1 machine</small>
  </div>
</li>
"""
        package = "x11-libs/libdrm-2.4.118"
        machines = ["babette"]
        context = package_row(package, machines)
        template = get_template("gentoo_build_publisher/package_row.html")
        result = template.render(context)
        self.assertEqual(result, expected)
