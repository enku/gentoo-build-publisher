"""Tests for the gbp apikey subcommand"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import datetime as dt
from argparse import ArgumentParser, Namespace
from dataclasses import replace

from django.conf import settings
from unittest_fixtures import Fixtures, given, where

import gbp_testkit.fixtures as testkit
from gbp_testkit import DjangoTestCase, TestCase
from gbp_testkit.helpers import LOCAL_TIMEZONE
from gentoo_build_publisher import publisher, utils
from gentoo_build_publisher.cli import apikey
from gentoo_build_publisher.django.gentoo_build_publisher import models
from gentoo_build_publisher.types import ApiKey
from gentoo_build_publisher.utils import time


@given(testkit.console, gbp=testkit.patch, create_secret_key=testkit.patch)
@where(create_secret_key__target="gentoo_build_publisher.cli.apikey.create_secret_key")
class GBPCreateTests(DjangoTestCase):
    def test_create_api_key_with_given_name(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        namespace = Namespace(action="create", name="test")

        status = apikey.handler(namespace, fixtures.gbp, console)

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
        apikey.handler(Namespace(action="create", name="TEST"), fixtures.gbp, console)

        self.assertFalse(models.ApiKey.objects.filter(name="TEST").exists())
        self.assertTrue(models.ApiKey.objects.filter(name="test").exists())

    def test_name_already_exists(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        api_key = ApiKey(
            name="test", key=apikey.create_api_key(), created=time.localtime()
        )
        publisher.repo.api_keys.save(api_key)

        status = apikey.handler(
            Namespace(action="create", name="TEST"), fixtures.gbp, console
        )

        self.assertEqual(status, 1)
        self.assertEqual(
            console.err.file.getvalue(), "An API key with that name already exists.\n"
        )
        self.assertTrue(models.ApiKey.objects.filter(name="test").exists())
        self.assertFalse(models.ApiKey.objects.filter(name="TEST").exists())

    def test_create_empty_name(self, fixtures: Fixtures) -> None:
        console = fixtures.console

        status = apikey.handler(
            Namespace(action="create", name=""), fixtures.gbp, console
        )

        self.assertEqual(status, 2)
        self.assertEqual(console.err.file.getvalue(), "''\n")

    def test_create_badchars_in_name(self, fixtures: Fixtures) -> None:
        console = fixtures.console

        status = apikey.handler(
            Namespace(action="create", name="b😈d"), fixtures.gbp, console
        )

        self.assertEqual(status, 2)
        self.assertEqual(console.err.file.getvalue(), "'b😈d'\n")

    def test_create_name_too_long(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        name = "x" * 129

        status = apikey.handler(
            Namespace(action="create", name=name), fixtures.gbp, console
        )

        self.assertEqual(status, 2)
        self.assertEqual(
            console.err.file.getvalue(),
            "'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            "xxxxxxxxxxxxxxx\nxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'\n",
        )

    def test_root_key(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        fixtures.create_secret_key.return_value = b"thisisatest"

        status = apikey.handler(
            Namespace(action="create", name="root"), fixtures.gbp, console
        )

        self.assertEqual(status, 0)
        self.assertFalse(models.ApiKey.objects.filter(name="root").exists())
        self.assertEqual(console.out.file.getvalue(), "thisisatest\n")


@given(testkit.console, local_timezone=testkit.patch, gbp=testkit.patch)
@where(local_timezone__target="gentoo_build_publisher.utils.time.LOCAL_TIMEZONE")
@where(local_timezone__new=LOCAL_TIMEZONE)
class GBPListTests(DjangoTestCase):
    def test(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        timestamp = dt.datetime(2024, 2, 22, 22, 0, tzinfo=dt.UTC)
        for name in ["this", "that", "the", "other"]:
            api_key = ApiKey(name=name, key=apikey.create_api_key(), created=timestamp)
            publisher.repo.api_keys.save(api_key)

        publisher.repo.api_keys.save(replace(api_key, last_used=timestamp))

        status = apikey.handler(Namespace(action="list"), fixtures.gbp, console)

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

        status = apikey.handler(Namespace(action="list"), fixtures.gbp, console)

        self.assertEqual(status, 0)
        self.assertEqual(console.out.file.getvalue(), "No API keys registered.\n")


@given(testkit.tmpdir, testkit.publisher, testkit.api_keys, testkit.console)
@given(gbp=testkit.patch)
@where(api_keys__names=["this", "that", "the", "other"])
class GBPDeleteTests(DjangoTestCase):
    def test_delete(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        namespace = Namespace(action="delete", name="that")

        status = apikey.handler(namespace, fixtures.gbp, console)

        self.assertEqual(status, 0)
        key_query = models.ApiKey.objects.filter(name="that")
        self.assertFalse(key_query.exists(), "key not deleted")

    def test_delete_is_case_insensitive(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        namespace = Namespace(action="delete", name="THAT")

        status = apikey.handler(namespace, fixtures.gbp, console)

        self.assertEqual(status, 0)
        key_query = models.ApiKey.objects.filter(name="that")
        self.assertFalse(key_query.exists(), "key not deleted")

    def test_delete_name_does_not_exist(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        namespace = Namespace(action="delete", name="bogus")

        status = apikey.handler(namespace, fixtures.gbp, console)

        self.assertEqual(status, 3)
        self.assertEqual(console.err.file.getvalue(), "No key exists with that name.\n")


@given(testkit.console, gbp=testkit.patch)
class GBPAPIKeyTests(TestCase):
    def test_unknown_action(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        namespace = Namespace(action="bogus")

        status = apikey.handler(namespace, fixtures.gbp, console)

        self.assertEqual(status, 255)
        self.assertEqual(console.err.file.getvalue(), "Unknown action: bogus\n")


class ParseArgs(TestCase):
    def test(self) -> None:
        parser = ArgumentParser()

        apikey.parse_args(parser)


@given(action=testkit.patch, parser=testkit.patch, parsed_args=testkit.patch)
class KeyNamesTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        names = ["this", "that", "the", "other"]

        for name in names:
            api_key = ApiKey(
                name=name, key=apikey.create_api_key(), created=time.localtime()
            )
            publisher.repo.api_keys.save(api_key)

        response = apikey.key_names(
            prefix="",
            action=fixtures.action,
            parser=fixtures.parser,
            parsed_args=fixtures.parsed_args,
        )

        self.assertEqual(response, sorted(names))
