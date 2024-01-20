"""Tests for the gentoo_build_publisher.utils module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from contextlib import contextmanager
from typing import Generator
from unittest import TestCase, mock

import requests
import requests.api
import requests.exceptions

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


class CPVToPathTestCase(TestCase):
    def test(self) -> None:
        cpv = "app-vim/gentoo-syntax-1"
        path = utils.cpv_to_path(cpv)

        self.assertEqual("app-vim/gentoo-syntax/gentoo-syntax-1-1.gpkg.tar", path)

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


class RequestAndRaiseTests(TestCase):
    """Tests for the request_and_raise function"""

    def test_returns_requests_response(self) -> None:
        with returns_response(200) as mock_request:
            response = utils.request_and_raise(requests.get, "http://tests.invalid/")

        # have no idea why pylint things mock_request is a dict
        # pylint: disable=no-member
        self.assertEqual(response, mock_request.return_value)
        self.assertEqual(response.status_code, 200)

    def test_raises_for_error_response(self) -> None:
        with returns_response(404):
            with self.assertRaises(requests.exceptions.HTTPError):
                utils.request_and_raise(requests.get, "http://test.invalid/")

    def test_honors_exclude(self) -> None:
        with returns_response(404):
            response = utils.request_and_raise(
                requests.get, "http://test.invalid/", exclude=[404]
            )

        self.assertEqual(response.status_code, 404)

    def test_honors_exclude2(self) -> None:
        with returns_response(401):
            with self.assertRaises(requests.exceptions.HTTPError) as ctx:
                utils.request_and_raise(
                    requests.get, "http://test.invalid/", exclude=[404]
                )

        self.assertEqual(ctx.exception.response.status_code, 401)


@contextmanager
def returns_response(status_code: int) -> Generator[mock.MagicMock, None, None]:
    patch = mock.patch.object(requests.api, "request")
    mock_request = patch.start()
    response = mock_request.return_value = mock.MagicMock(
        spec=requests.Response, reason="testing", url="http://test.invalid/"
    )
    response.raise_for_status.side_effect = lambda: requests.Response.raise_for_status(
        response
    )
    response.status_code = status_code

    yield mock_request

    patch.stop()
