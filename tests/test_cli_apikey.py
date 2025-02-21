"""Tests for the gbp apikey subcommand"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import datetime as dt
from argparse import ArgumentParser, Namespace
from dataclasses import replace
from unittest.mock import Mock, patch

from django.conf import settings
from gbp_testkit import DjangoTestCase, TestCase
from gbp_testkit.helpers import LOCAL_TIMEZONE
from unittest_fixtures import Fixtures, given, where

from gentoo_build_publisher import models, publisher, utils
from gentoo_build_publisher.cli import apikey
from gentoo_build_publisher.types import ApiKey
from gentoo_build_publisher.utils import time


@given("console")
class GBPCreateTests(DjangoTestCase):
    def test_create_api_key_with_given_name(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        mock_gbp = Mock(name="gbp")
        namespace = Namespace(action="create", name="test")

        status = apikey.handler(namespace, mock_gbp, console)

        self.assertEqual(status, 0)
        key = console.out.file.getvalue().strip()

        record = models.ApiKey.objects.get(name="test")
        self.assertEqual(record.name, "test")
        self.assertEqual(record.last_used, None)
        self.assertEqual(
            utils.decrypt(record.apikey, settings.SECRET_KEY.encode("ascii")).decode(
                "ascii"
            ),
            key,
        )

    def test_name_is_case_insensitive(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        apikey.handler(Namespace(action="create", name="TEST"), Mock(), console)

        self.assertFalse(models.ApiKey.objects.filter(name="TEST").exists())
        self.assertTrue(models.ApiKey.objects.filter(name="test").exists())

    def test_name_already_exists(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        api_key = ApiKey(
            name="test", key=apikey.create_api_key(), created=time.localtime()
        )
        publisher.repo.api_keys.save(api_key)

        status = apikey.handler(
            Namespace(action="create", name="TEST"), Mock(), console
        )

        self.assertEqual(status, 1)
        self.assertEqual(
            console.err.file.getvalue(), "An API key with that name already exists.\n"
        )
        self.assertTrue(models.ApiKey.objects.filter(name="test").exists())
        self.assertFalse(models.ApiKey.objects.filter(name="TEST").exists())

    def test_create_empty_name(self, fixtures: Fixtures) -> None:
        console = fixtures.console

        status = apikey.handler(Namespace(action="create", name=""), Mock(), console)

        self.assertEqual(status, 2)
        self.assertEqual(console.err.file.getvalue(), "''\n")

    def test_create_badchars_in_name(self, fixtures: Fixtures) -> None:
        console = fixtures.console

        status = apikey.handler(
            Namespace(action="create", name="b😈d"), Mock(), console
        )

        self.assertEqual(status, 2)
        self.assertEqual(console.err.file.getvalue(), "'b😈d'\n")

    def test_create_name_too_long(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        name = "x" * 129

        status = apikey.handler(Namespace(action="create", name=name), Mock(), console)

        self.assertEqual(status, 2)
        self.assertEqual(
            console.err.file.getvalue(),
            "'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            "xxxxxxxxxxxxxxx\nxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'\n",
        )

    @patch("gentoo_build_publisher.cli.apikey.create_secret_key")
    def test_root_key(self, create_secret_key: Mock, fixtures: Fixtures) -> None:
        console = fixtures.console
        gbp = Mock()
        create_secret_key.return_value = b"thisisatest"

        status = apikey.handler(Namespace(action="create", name="root"), gbp, console)

        self.assertEqual(status, 0)
        self.assertFalse(models.ApiKey.objects.filter(name="root").exists())
        self.assertEqual(console.out.file.getvalue(), "thisisatest\n")


@given("console")
@patch("gentoo_build_publisher.utils.time.LOCAL_TIMEZONE", new=LOCAL_TIMEZONE)
class GBPListTests(DjangoTestCase):
    def test(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        timestamp = dt.datetime(2024, 2, 22, 22, 0, tzinfo=dt.UTC)
        for name in ["this", "that", "the", "other"]:
            api_key = ApiKey(name=name, key=apikey.create_api_key(), created=timestamp)
            publisher.repo.api_keys.save(api_key)

        publisher.repo.api_keys.save(replace(api_key, last_used=timestamp))

        gbp = Mock()

        status = apikey.handler(Namespace(action="list"), gbp, console)

        self.assertEqual(status, 0)
        expected = """\
╭───────┬───────────────────╮
│ Name  │ Last Used         │
├───────┼───────────────────┤
│ other │ 02/22/24 15:00:00 │
│ that  │ Never             │
│ the   │ Never             │
│ this  │ Never             │
╰───────┴───────────────────╯
"""
        self.assertEqual(console.out.file.getvalue(), expected)

    def test_with_no_keys(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        gbp = Mock()

        status = apikey.handler(Namespace(action="list"), gbp, console)

        self.assertEqual(status, 0)
        self.assertEqual(console.out.file.getvalue(), "No API keys registered.\n")


@given("tmpdir", "publisher", "api_keys", "console")
@where(api_keys={"api_key_names": ["this", "that", "the", "other"]})
class GBPDeleteTests(DjangoTestCase):
    def test_delete(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        namespace = Namespace(action="delete", name="that")

        status = apikey.handler(namespace, Mock(), console)

        self.assertEqual(status, 0)
        key_query = models.ApiKey.objects.filter(name="that")
        self.assertFalse(key_query.exists(), "key not deleted")

    def test_delete_is_case_insensitive(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        namespace = Namespace(action="delete", name="THAT")

        status = apikey.handler(namespace, Mock(), console)

        self.assertEqual(status, 0)
        key_query = models.ApiKey.objects.filter(name="that")
        self.assertFalse(key_query.exists(), "key not deleted")

    def test_delete_name_does_not_exist(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        namespace = Namespace(action="delete", name="bogus")

        status = apikey.handler(namespace, Mock(), console)

        self.assertEqual(status, 3)
        self.assertEqual(console.err.file.getvalue(), "No key exists with that name.\n")


@given("console")
class GBPAPIKeyTests(TestCase):
    def test_unknown_action(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        namespace = Namespace(action="bogus")

        status = apikey.handler(namespace, Mock(), console)

        self.assertEqual(status, 255)
        self.assertEqual(console.err.file.getvalue(), "Unknown action: bogus\n")


class ParseArgs(TestCase):
    def test(self) -> None:
        parser = ArgumentParser()

        apikey.parse_args(parser)


class KeyNamesTests(TestCase):
    def test(self) -> None:
        names = ["this", "that", "the", "other"]

        for name in names:
            api_key = ApiKey(
                name=name, key=apikey.create_api_key(), created=time.localtime()
            )
            publisher.repo.api_keys.save(api_key)

        response = apikey.key_names(
            prefix="", action=Mock(), parser=Mock(), parsed_args=Mock()
        )

        self.assertEqual(response, sorted(names))
