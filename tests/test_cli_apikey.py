"""Tests for the gbp apikey subcommand"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import datetime as dt
from argparse import ArgumentParser, Namespace
from unittest.mock import Mock, patch

from django.conf import settings

from gentoo_build_publisher import models, utils
from gentoo_build_publisher.cli import apikey

from . import LOCAL_TIMEZONE, DjangoTestCase, TestCase, string_console


class GBPCreateTests(DjangoTestCase):
    def test_create_api_key_with_given_name(self) -> None:
        console, stdout, *_ = string_console()
        mock_gbp = Mock(name="gbp")
        namespace = Namespace(action="create", name="test")

        status = apikey.handler(namespace, mock_gbp, console)

        self.assertEqual(status, 0)
        key = stdout.getvalue().strip()

        record = models.ApiKey.objects.get(name="test")
        self.assertEqual(record.name, "test")
        self.assertEqual(record.last_used, None)
        self.assertEqual(
            utils.decrypt(record.apikey, settings.SECRET_KEY.encode("ascii")).decode(
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
    def test_root_key(self, create_secret_key: Mock) -> None:
        console, stdout, *_ = string_console()
        gbp = Mock()
        create_secret_key.return_value = b"thisisatest"

        status = apikey.handler(Namespace(action="create", name="root"), gbp, console)

        self.assertEqual(status, 0)
        self.assertFalse(models.ApiKey.objects.filter(name="root").exists())
        self.assertEqual(stdout.getvalue(), "thisisatest\n")


@patch("gentoo_build_publisher.utils.time.LOCAL_TIMEZONE", new=LOCAL_TIMEZONE)
class GBPListTests(DjangoTestCase):
    def test(self) -> None:
        console, stdout, *_ = string_console()
        for name in ["this", "that", "the", "other"]:
            record = apikey.save_api_key(apikey.create_api_key(), name)
        record.last_used = dt.datetime(2024, 2, 22, 22, 0, tzinfo=dt.UTC)
        record.save()

        gbp = Mock()

        status = apikey.handler(Namespace(action="list"), gbp, console)

        self.assertEqual(status, 0)
        expected = """\
╭───────┬───────────────────╮
│ Name  │ Last Used         │
├───────┼───────────────────┤
│ this  │ Never             │
│ that  │ Never             │
│ the   │ Never             │
│ other │ 02/22/24 15:00:00 │
╰───────┴───────────────────╯
"""
        self.assertEqual(stdout.getvalue(), expected)

    def test_with_no_keys(self) -> None:
        console, stdout, *_ = string_console()
        gbp = Mock()

        status = apikey.handler(Namespace(action="list"), gbp, console)

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), "No API keys registered.\n")


class GBPDeleteTests(DjangoTestCase):
    def setUp(self) -> None:
        super().setUp()

        for name in ["this", "that", "the", "other"]:
            apikey.save_api_key(apikey.create_api_key(), name)

    def test_delete(self) -> None:
        console, *_ = string_console()
        namespace = Namespace(action="delete", name="that")

        status = apikey.handler(namespace, Mock(), console)

        self.assertEqual(status, 0)
        key_query = models.ApiKey.objects.filter(name="that")
        self.assertFalse(key_query.exists(), "key not deleted")

    def test_delete_is_case_insensitive(self) -> None:
        console, *_ = string_console()
        namespace = Namespace(action="delete", name="THAT")

        status = apikey.handler(namespace, Mock(), console)

        self.assertEqual(status, 0)
        key_query = models.ApiKey.objects.filter(name="that")
        self.assertFalse(key_query.exists(), "key not deleted")

    def test_delete_name_does_not_exist(self) -> None:
        console, _, stderr = string_console()
        namespace = Namespace(action="delete", name="bogus")

        status = apikey.handler(namespace, Mock(), console)

        self.assertEqual(status, 3)
        self.assertEqual(stderr.getvalue(), "No key exists with that name.\n")


class GBPAPIKeyTests(TestCase):
    def test_unknown_action(self) -> None:
        console, _, stderr = string_console()
        namespace = Namespace(action="bogus")

        status = apikey.handler(namespace, Mock(), console)

        self.assertEqual(status, 255)
        self.assertEqual(stderr.getvalue(), "Unknown action: bogus\n")


class ParseArgs(TestCase):
    def test(self) -> None:
        parser = ArgumentParser()

        apikey.parse_args(parser)


class ValidateKeyNameTests(TestCase):
    def test(self) -> None:
        apikey.validate_key_name("bob")

    def test_empty_string(self) -> None:
        with self.assertRaises(apikey.KeyNameError):
            apikey.validate_key_name("")

    def test_too_long(self) -> None:
        with self.assertRaises(apikey.KeyNameError):
            apikey.validate_key_name("x" * 256)

    def test_non_alphanumeric(self) -> None:
        with self.assertRaises(apikey.KeyNameError):
            apikey.validate_key_name("bob.6")
