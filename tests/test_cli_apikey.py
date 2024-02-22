"""Tests for the gbp apikey subcommand"""

# pylint: disable=missing-class-docstring,missing-function-docstring

from argparse import Namespace
from unittest.mock import Mock

from gentoo_build_publisher import models
from gentoo_build_publisher.cli import apikey

from . import TestCase, string_console


class GBPCreateTests(TestCase):
    def test_create_api_key_with_given_name(self) -> None:
        gbp = Mock()  # unused
        console, stdout, *_ = string_console()

        status = apikey.handler(Namespace(action="create", name="test"), gbp, console)

        self.assertEqual(status, 0)
        key = stdout.getvalue().strip()

        obj = models.ApiKey.objects.get(apikey=key)
        self.assertEqual(obj.name, "test")
        self.assertEqual(obj.last_used, None)
