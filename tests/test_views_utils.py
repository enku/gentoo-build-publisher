"""Tests for the dashboard utils"""

# pylint: disable=missing-docstring,unused-argument

from django.http import Http404, HttpRequest, HttpResponse
from unittest_fixtures import Fixtures, given, where

import gbp_testkit.fixtures as testkit
from gbp_testkit import DjangoTestCase, TestCase
from gentoo_build_publisher.django.gentoo_build_publisher.views.utils import (
    ViewFinder,
    color_range_from_settings,
    color_range_from_settings2,
    experimental,
    get_build_record_or_404,
    get_primary_colors,
    get_query_value_from_request,
    get_url_for_package,
    gradient_colors,
    view,
)
from gentoo_build_publisher.utils import Color

from .lib import create_builds_and_packages


@given(request=testkit.patch)
class GetQueryValueFromRequestTests(TestCase):
    def test_returns_fallback(self, fixtures: Fixtures) -> None:
        request = fixtures.request
        request.GET = {}
        chart_days = get_query_value_from_request(request, "chart_days", int, 10)

        self.assertEqual(chart_days, 10)

    def test_with_queryparam(self, fixtures: Fixtures) -> None:
        request = fixtures.request
        request.GET = {"chart_days": "10"}
        chart_days = get_query_value_from_request(request, "chart_days", int, 7)

        self.assertEqual(chart_days, 10)

    def test_with_invalid_queryparam(self, fixtures: Fixtures) -> None:
        request = fixtures.request
        request.GET = {"chart_days": "bogus"}
        chart_days = get_query_value_from_request(request, "chart_days", int, 10)

        self.assertEqual(chart_days, 10)


@given(testkit.pulled_builds)
class GetBuildRecordOr404Tests(TestCase):
    def test_with_build(self, fixtures: Fixtures) -> None:
        build = fixtures.builds[0]

        record = get_build_record_or_404(build.machine, build.build_id)

        self.assertEqual(type(record).__name__, "BuildRecord")
        self.assertEqual(
            (build.machine, build.build_id),
            (record.machine, record.build_id),
            "Record returned was not the one expected",
        )

    def test_without_build(self, fixtures: Fixtures) -> None:
        with self.assertRaises(Http404):
            get_build_record_or_404("bogus", "666")


@given(request=testkit.patch)
@where(request__spec=HttpRequest)
class ExperimentalMarkerTests(DjangoTestCase):
    def test_debug_is_false(self, fixtures: Fixtures) -> None:
        request = fixtures.request
        experimental_view = experimental(dummy_view)

        with self.settings(DEBUG=False):
            response = dummy_view(request)
            self.assertEqual(response.status_code, 200)

            with self.assertRaises(Http404):
                response = experimental_view(request)

    def test_debug_is_true(self, fixtures: Fixtures) -> None:
        request = fixtures.request
        experimental_view = experimental(dummy_view)

        with self.settings(DEBUG=True):
            response = dummy_view(request)
            self.assertEqual(response.status_code, 200)

            response = experimental_view(request)
            self.assertEqual(response.status_code, 200)


@given(testkit.publisher, pf=testkit.cpv_generator)
class GetPackageURLTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        builder = publisher.jenkins.artifact_builder
        [build] = create_builds_and_packages("babette", 1, 1, builder, fixtures.pf)
        publisher.pull(build)
        package = publisher.get_packages(build)[-1]
        request = HttpRequest()
        request.META["SERVER_NAME"] = "testserver"
        request.META["SERVER_PORT"] = 80

        url = get_url_for_package(build, package, request)
        cpvb = package.cpvb()
        cat, rest = cpvb.split("/", 1)
        pkg, vb = rest.split("-", 1)
        expected = f"http://testserver/binpkgs/{build}/{cat}/{pkg}/{pkg}-{vb}.gpkg.tar"
        self.assertEqual(url, expected)


@given(views=testkit.patch)
@where(views__object=ViewFinder, views__target="pattern_views")
@where(views__new_callable=list)
class ViewFinderTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        self.assertEqual(ViewFinder.pattern_views, [])

    def test_register_views(self, fixtures: Fixtures) -> None:
        @view("/foo", name="foo")
        def foo_view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("")  # pragma: no cover

        self.assertEqual(len(ViewFinder.pattern_views), 1)
        urlpattern = ViewFinder.pattern_views[0]
        self.assertEqual(urlpattern.name, "foo")
        self.assertEqual(urlpattern.callback, foo_view)
        self.assertEqual(str(urlpattern.pattern), "/foo")

        @view("/bar", name="bar")
        def bar_view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("")  # pragma: no cover

        self.assertEqual(len(ViewFinder.pattern_views), 2)
        urlpattern = ViewFinder.pattern_views[1]
        self.assertEqual(urlpattern.name, "bar")
        self.assertEqual(urlpattern.callback, bar_view)
        self.assertEqual(str(urlpattern.pattern), "/bar")


@given(settings=testkit.patch)
@where(
    settings__target="gentoo_build_publisher.django.gentoo_build_publisher.views.utils.GBP_SETTINGS"
)
@where(settings__new_callable=dict)
class ColorRangeFromSettingsTests(TestCase):
    def test_gradient(self, fixtures: Fixtures) -> None:
        settings = fixtures.settings
        settings["COLOR_START"] = (255, 0, 0)
        settings["COLOR_END"] = (0, 255, 255)

        color_range = color_range_from_settings()

        self.assertEqual(
            color_range,
            (Color(red=255, green=0, blue=0), Color(red=0, green=255, blue=255)),
        )

    def test_multi_color(self, fixtures: Fixtures) -> None:
        settings = fixtures.settings
        settings["COLOR_START"] = ((255, 0, 0), (255, 255, 255), (0, 0, 255))
        settings["COLOR_END"] = (128, 128, 128)  # ignored

        color_range = color_range_from_settings()

        self.assertEqual(
            color_range, (Color(red=255, green=0, blue=0), Color(0, 0, 255))
        )

    def test_colors_setting(self, fixtures: Fixtures) -> None:
        settings = fixtures.settings
        settings["COLORS"] = ((255, 0, 0), (255, 255, 255), (0, 0, 255))
        settings["COLOR_START"] = ((0, 0, 255), (255, 255, 255), (255, 0, 0))

        color_range = color_range_from_settings()

        self.assertEqual(color_range, (Color(255, 0, 0), Color(0, 0, 255)))


@given(settings=testkit.patch)
@where(
    settings__target="gentoo_build_publisher.django.gentoo_build_publisher.views.utils.GBP_SETTINGS"
)
@where(settings__new_callable=dict)
class ColorRangeFromSettings2Tests(TestCase):
    def test_gradient(self, fixtures: Fixtures) -> None:
        settings = fixtures.settings
        settings["COLOR_START"] = (255, 0, 0)
        settings["COLOR_END"] = (0, 255, 255)

        color_range = color_range_from_settings2()

        self.assertEqual(
            color_range,
            (Color(red=255, green=0, blue=0), Color(red=0, green=255, blue=255)),
        )

    def test_multi_color(self, fixtures: Fixtures) -> None:
        settings = fixtures.settings
        settings["COLOR_START"] = ((255, 0, 0), (255, 255, 255), (0, 0, 255))
        settings["COLOR_END"] = (128, 128, 128)  # ignored

        color_range = color_range_from_settings2()

        self.assertEqual(
            color_range,
            (Color(red=255, green=0, blue=0), Color(255, 255, 255), Color(0, 0, 255)),
        )

    def test_colors_setting(self, fixtures: Fixtures) -> None:
        settings = fixtures.settings
        settings["COLORS"] = ((255, 0, 0), (255, 255, 255), (0, 0, 255))
        settings["COLOR_START"] = ((0, 0, 255), (255, 255, 255), (255, 0, 0))

        color_range = color_range_from_settings2()

        self.assertEqual(
            color_range, (Color(255, 0, 0), Color(255, 255, 255), Color(0, 0, 255))
        )


class GradientColors(TestCase):
    def test_two_colors(self) -> None:
        colors = gradient_colors(Color(0, 0, 255), Color(255, 255, 255), 10)

        self.assertEqual(
            colors,
            [
                "#0000ff",
                "#1c1cff",
                "#3838ff",
                "#5555ff",
                "#7171ff",
                "#8d8dff",
                "#aaaaff",
                "#c6c6ff",
                "#e2e2ff",
                "#ffffff",
            ],
        )


class GetPrimaryColorsTests(TestCase):
    def test_with_two_color_gradient(self) -> None:
        colors = get_primary_colors([Color(0, 0, 255), Color(255, 255, 255)], 10)

        self.assertEqual(
            colors,
            [
                "#0000ff",
                "#1c1cff",
                "#3838ff",
                "#5555ff",
                "#7171ff",
                "#8d8dff",
                "#aaaaff",
                "#c6c6ff",
                "#e2e2ff",
                "#ffffff",
            ],
        )

    def test_multi_color(self) -> None:
        colors = get_primary_colors(
            [Color(255, 0, 0), Color(255, 255, 255), Color(0, 0, 255)], 3
        )

        self.assertEqual(colors, ["#ff0000", "#ffffff", "#0000ff"])

    def test_size_is_greater_than_given_colors(self) -> None:
        colors = get_primary_colors(
            [Color(255, 0, 0), Color(255, 255, 255), Color(0, 0, 255)], 5
        )

        self.assertEqual(
            colors,
            ["#ff0000"] + gradient_colors(Color(255, 255, 255), Color(0, 0, 255), 4),
        )

    def test_size_is_less_than_given_colors(self) -> None:
        colors = get_primary_colors(
            [Color(255, 0, 0), Color(255, 255, 255), Color(0, 0, 255)], 2
        )

        self.assertEqual(colors, ["#ff0000", "#ffffff"])


def dummy_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("Hi!")
