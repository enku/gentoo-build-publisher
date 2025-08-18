"""Tests for custom template tags"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
from typing import Any
from unittest import TestCase

from django.template import Context, Template, TemplateSyntaxError
from unittest_fixtures import Fixtures, given, where

from gbp_testkit import fixtures as testkit
from gbp_testkit.helpers import LOCAL_TIMEZONE
from gentoo_build_publisher import publisher
from gentoo_build_publisher.types import Content
from gentoo_build_publisher.utils.time import localtime

NOW = "gentoo_build_publisher.utils.time.now"


class TemplateTagTests(TestCase):
    library = "gbp"
    template = "override me!"

    def render(self, template: str | None = None, **kwargs: Any) -> str:
        template = self.template if template is None else template
        context = Context(kwargs)
        return Template(f"{{% load {self.library} %}}{template}").render(context)


class NumberizeTestCase(TemplateTagTests):
    template = "{{ number|numberize:precision }}"

    def test_should_return_whole_number_when_precision_0(self) -> None:
        result = self.render(number=96_858_412, precision=0)

        self.assertEqual(result, "97M")

    def test_number_less_than_1000(self) -> None:
        result = self.render(number=968, precision=2)

        self.assertEqual(result, "968")

    def test_number_less_than_1_000_000(self) -> None:
        result = self.render(number=968_584, precision=1)

        self.assertEqual(result, "968.6k")

    def test_number_less_than_1_000_000_000(self) -> None:
        result = self.render(number=96_858_412, precision=2)

        self.assertEqual(result, "96.86M")

    def test_number_greater_than_1_000_000_000(self) -> None:
        result = self.render(number=6_123_000_548, precision=2)

        self.assertEqual(result, "6.12G")

    def test_invalid_value(self) -> None:
        with self.assertRaises(TemplateSyntaxError):
            self.render(number="this is not a number", precision=2)

    def test_number_greater_than_1_000_000_000_binary(self) -> None:
        result = self.render(number=6_123_000_548, precision="b2")
        self.assertEqual(result, "5.70G")

        result = self.render(number=6_123_000_548, precision="b")
        self.assertEqual(result, "6G")

    def test_1024_binary_vs_decimal(self) -> None:
        result = self.render(number=1024, precision=3)
        self.assertEqual(result, "1.024k")

        result = self.render(number=1024, precision="b3")
        self.assertEqual(result, "1k")


class NumberedCircleTests(TemplateTagTests):
    template = "{% circle build_count name color %}"

    def test(self) -> None:
        expected = """\
<div class="col-lg-4" align="center">
  <svg class="bd-placeholder-img rounded-circle" width="140" height="140" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" focusable="false" role="img"><rect width="100%" height="100%" fill="#755245"/><text x="50%" y="50%" fill="#fff" dy=".3em" font-size="50px">452</text></svg>
  <h2>Builds</h2>
</div>
"""
        result = self.render(build_count=452, name="Builds", color="#755245")
        self.assertEqual(result, expected)

    def test_large_number(self) -> None:
        expected = """\
<div class="col-lg-4" align="center">
  <svg class="bd-placeholder-img rounded-circle" width="140" height="140" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" focusable="false" role="img"><title>212351</title><rect width="100%" height="100%" fill="#755245"/><text x="50%" y="50%" fill="#fff" dy=".3em" font-size="50px">212k</text></svg>
  <h2>Packages</h2>
</div>
"""
        result = self.render(build_count=212351, name="Packages", color="#755245")
        self.assertEqual(result, expected)


class ChartTests(TemplateTagTests):
    template = "{% chart dom_id title cols=cols width=width height=height %}"

    def test(self) -> None:
        expected = """\
<div class="col-md-8">
  <h4 class="d-flex justify-content-between align-items-center mb-3">Test Test</h4>
  <canvas id="testChart" width="100" height="150"></canvas>
</div>
"""
        result = self.render(
            dom_id="testChart", title="Test Test", cols=8, width=100, height=150
        )
        self.assertEqual(result, expected)


@given(testkit.record, testkit.publisher)
@where(records_db__backend="django")
class BuildRowTests(TemplateTagTests):
    template = "{% build_row build build_packages %}"

    def test(self, fixtures: Fixtures) -> None:
        # pylint: disable=line-too-long
        build = fixtures.record
        machine = build.machine
        id = build.build_id  # pylint: disable=redefined-builtin
        expected = f"""\
<li class="list-group-item d-flex justify-content-between lh-condensed">
  <div>
    <h6 class="my-0"><a class="machine-link" href="/machines/{machine}/">{machine}</a></h6>
    <small class="text-muted"><a class="build-link" href="/machines/{machine}/builds/{id}/">{id}</a></small>
  </div>
  <span title="Packages" class="text-muted" data-bs-toggle="popover" data-bs-trigger="hover focus" data-bs-content='x11-libs/libdrm-2.4.118&lt;br/&gt;x11-misc/xkeyboard-config-2.40-r1' data-bs-html="true">2 packages</span>
</li>
"""
        packages = ["x11-libs/libdrm-2.4.118", "x11-misc/xkeyboard-config-2.40-r1"]
        build_packages = {str(build): packages}
        result = self.render(build=build, build_packages=build_packages)
        self.assertEqual(result, expected)


class PackageRowTests(TemplateTagTests):
    template = "{% package_row package machines %}"

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
        result = self.render(package=package, machines=machines)
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
        result = self.render(package=package, machines=machines)
        self.assertEqual(result, expected)


class RoundRectTests(TemplateTagTests):
    template = "{% roundrect text title color %}"

    def test(self) -> None:
        expected = """
<div class="col" align="center"><svg class="bd-placeholder-img rounded" width="100%" height="140" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" focusable="false" role="img"><rect width="100%" height="100%" fill="#572554"/><text x="50%" y="50%" fill="#fff" dy=".3em" font-size="50px" letter-spacing="8">lighthouse</text></svg></div>
"""
        result = self.render(text="lighthouse", title="", color="#572554")
        self.assertEqual(result, expected)

    def test_with_title(self) -> None:
        expected = """
<div class="col" align="center"><svg class="bd-placeholder-img rounded" width="100%" height="140" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" focusable="false" role="img"><title>This is a test</title><rect width="100%" height="100%" fill="#572554"/><text x="50%" y="50%" fill="#fff" dy=".3em" font-size="50px" letter-spacing="8">lighthouse</text></svg></div>
"""

        result = self.render(text="lighthouse", title="This is a test", color="#572554")
        self.assertEqual(result, expected)

    def test_with_scale(self) -> None:
        template = "{% roundrect text title color scale %}"
        expected = """
<div class="col" align="center"><svg class="bd-placeholder-img rounded" width="100%" height="70" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" focusable="false" role="img"><rect width="100%" height="100%" fill="#572554"/><text x="50%" y="50%" fill="#fff" dy=".3em" font-size="25px" letter-spacing="4">lighthouse</text></svg></div>
"""
        result = self.render(
            template=template, text="lighthouse", title="", color="#572554", scale=0.5
        )

        self.assertEqual(result, expected)


class MachineLinkTests(TemplateTagTests):
    def test_renders_link(self) -> None:
        expected = '<a class="machine-link" href="/machines/lighthouse/">lighthouse</a>'
        self.assertEqual(self.render("{{ 'lighthouse'|machine_link }}"), expected)


@given(now=testkit.patch)
@where(now__target=NOW, now__return_value=dt.datetime(2024, 1, 11, 20, 54))
@given(localtimezone=testkit.patch)
@where(localtimezone__target="gentoo_build_publisher.utils.time.LOCAL_TIMEZONE")
@where(localtimezone__new=LOCAL_TIMEZONE)
class DisplayTimeTests(TemplateTagTests):
    # pylint: disable=unused-argument
    template = "{{ timestamp|display_time }}"

    def test_same_day(self, fixtures: Fixtures) -> None:
        timestamp = localtime(dt.datetime(2024, 1, 11, 8, 54))

        self.assertEqual(self.render(timestamp=timestamp), "07:54:00")

    def test_previous_day(self, fixtures: Fixtures) -> None:
        timestamp = localtime(dt.datetime(2024, 1, 10, 8, 54))

        self.assertEqual(self.render(timestamp=timestamp), "Jan 10 07:54")

    def test_previous_week(self, fixtures: Fixtures) -> None:
        timestamp = localtime(dt.datetime(2024, 1, 4, 8, 54))

        self.assertEqual(self.render(timestamp=timestamp), "Jan 4")


@given(testkit.record, testkit.publisher)
@where(records_db__backend="django")
class BuildLinkTests(TemplateTagTests):
    def test_renders_link(self, fixtures: Fixtures) -> None:
        build = fixtures.record
        machine = build.machine
        id = build.build_id  # pylint: disable=redefined-builtin

        expected = (
            f'<a class="build-link" href="/machines/{machine}/builds/{id}/">{id}</a>'
        )
        self.assertEqual(self.render("{{ build|build_link }}", build=build), expected)

    def test_with_build_note(self, fixtures: Fixtures) -> None:
        build = fixtures.record
        build = publisher.repo.build_records.save(build, note="This is a test")
        machine = build.machine
        id = build.build_id  # pylint: disable=redefined-builtin

        expected = (
            f'<a class="build-link" href="/machines/{machine}/builds/{id}/">{id}</a> 🗒'
        )
        self.assertEqual(self.render("{{ build|build_link }}", build=build), expected)

    def test_with_tags(self, fixtures: Fixtures) -> None:
        build = fixtures.record
        machine = build.machine
        publisher.pull(build)
        publisher.tag(build, "foo")
        publisher.tag(build, "bar")
        build = publisher.record(build)
        id = build.build_id  # pylint: disable=redefined-builtin

        expected = (
            f'<a class="build-link" href="/machines/{machine}/builds/{id}/">{id}</a>'
            ' <span class="tags">@bar @foo</span>'
        )
        self.assertEqual(self.render("{{ build|build_link }}", build=build), expected)

    def test_published(self, fixtures: Fixtures) -> None:
        build = fixtures.record
        machine = build.machine
        id = build.build_id  # pylint: disable=redefined-builtin
        publisher.pull(build)
        publisher.publish(build)
        build = publisher.record(build)

        expected = (
            "<b>"
            f'<a class="build-link" href="/machines/{machine}/builds/{id}/">{id}</a>'
            "</b>"
        )
        self.assertEqual(self.render("{{ build|build_link }}", build=build), expected)


@given(testkit.build)
class BuildWithSlashTests(TemplateTagTests):
    def test(self, fixtures: Fixtures) -> None:
        self.assertEqual(
            self.render("{{ build|build_with_slash }}", build=fixtures.build),
            f"babette/{fixtures.build.build_id}",
        )


@given(testkit.record, testkit.publisher)
@where(records_db__backend="django")
class MachineBuildRowTests(TemplateTagTests):
    template = "{% machine_build_row build %}"

    def test(self, fixtures: Fixtures) -> None:
        b = fixtures.record
        publisher.pull(b)

        # pylint: disable=line-too-long
        expected = f"""
<li class="list-group-item d-flex justify-content-between lh-condensed">
  <div>
    <h6 class="my-0"><a class="build-link" href="/machines/{b.machine}/builds/{b.build_id}/">{b.build_id}</a></h6>"""
        self.assertTrue(self.render(build=fixtures.record).startswith(expected))

    def test_missing_gbp_dot_json(self, fixtures: Fixtures) -> None:
        # Older (2021-ish) builds don't have a gbp.json file
        build = fixtures.record
        publisher.pull(build)
        repos = publisher.storage.get_path(build, Content.BINPKGS)
        gbp_json = repos.joinpath("gbp.json")
        gbp_json.unlink()

        # We just want to ensure that this does not error out (LookupError).
        self.render(build=fixtures.record)
