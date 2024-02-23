"""Tests for the gbp apikey subcommand"""

# pylint: disable=missing-class-docstring,missing-function-docstring

from argparse import Namespace
from unittest.mock import Mock, patch

from django.conf import settings

from gentoo_build_publisher import models, utils
from gentoo_build_publisher.cli import apikey

from . import DjangoTestCase, string_console


class GBPCreateTests(DjangoTestCase):
    def test_create_api_key_with_given_name(self) -> None:
        console, stdout, *_ = string_console()
        mock_gbp = Mock(name="gbp")
        namespace = Namespace(action="create", name="test")

        status = apikey.handler(namespace, mock_gbp, console)

        self.assertEqual(status, 0)
        key = stdout.getvalue().strip()

        obj = models.ApiKey.objects.get(name="test")
        self.assertEqual(obj.name, "test")
        self.assertEqual(obj.last_used, None)
        self.assertEqual(
            utils.decrypt(obj.apikey, settings.SECRET_KEY.encode("ascii")).decode(
                "ascii"
            ),
            key,
        )

    def test_name_is_case_insensitive(self) -> None:
        apikey.handler(
            Namespace(action="create", name="TEST"), Mock(), string_console()[0]
        )

        self.assertFalse(models.ApiKey.objects.filter(name="TEST").exists())
        self.assertTrue(models.ApiKey.objects.filter(name="test").exists())

    def test_name_already_exists(self) -> None:
        console, _, stderr = string_console()
        apikey.save_api_key(apikey.create_api_key(), "test")

        status = apikey.handler(
            Namespace(action="create", name="TEST"), Mock(), console
        )

        self.assertEqual(status, 1)
        self.assertEqual(
            stderr.getvalue(), "An API key with that name already exists.\n"
        )
        self.assertTrue(models.ApiKey.objects.filter(name="test").exists())
        self.assertFalse(models.ApiKey.objects.filter(name="TEST").exists())

    def test_create_empty_name(self) -> None:
        console, _, stderr = string_console()

        status = apikey.handler(Namespace(action="create", name=""), Mock(), console)

        self.assertEqual(status, 2)
        self.assertEqual(stderr.getvalue(), "Key name must have at least 1 character\n")

    def test_create_badchars_in_name(self) -> None:
        console, _, stderr = string_console()

        status = apikey.handler(
            Namespace(action="create", name="b😈d"), Mock(), console
        )

        self.assertEqual(status, 2)
        self.assertEqual(
            stderr.getvalue(), "Key name must only contain alphanumeric characters\n"
        )

    def test_create_name_too_long(self) -> None:
        console, _, stderr = string_console()

        status = apikey.handler(
            Namespace(action="create", name="x" * 256), Mock(), console
        )

        self.assertEqual(status, 2)
        self.assertEqual(stderr.getvalue(), "Key name must not exceed 128 characters\n")

    @patch("gentoo_build_publisher.cli.apikey.create_secret_key")
    def test_root_key(self, create_secret_key) -> None:
        console, stdout, *_ = string_console()
        gbp = Mock()
        create_secret_key.return_value = b"thisisatest"

        status = apikey.handler(Namespace(action="create", name="root"), gbp, console)

        self.assertEqual(status, 0)
        self.assertFalse(models.ApiKey.objects.filter(name="root").exists())
        self.assertEqual(stdout.getvalue(), "thisisatest\n")
