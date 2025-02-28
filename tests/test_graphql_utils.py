"""Tests for graphql.utils"""

# pylint: disable=missing-docstring,unused-argument
import datetime as dt
import os
from typing import Any
from unittest import mock

from gbp_testkit import TestCase
from gbp_testkit.helpers import graphql
from graphql import GraphQLResolveInfo
from unittest_fixtures import Fixtures, given

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import apikey
from gentoo_build_publisher.graphql import resolvers, type_defs
from gentoo_build_publisher.graphql.utils import (
    UnauthorizedError,
    load_schema,
    require_apikey,
)
from gentoo_build_publisher.types import ApiKey
from gentoo_build_publisher.utils import encode_basic_auth_data

Mock = mock.Mock


@given("tmpdir", "publisher", "client")
class MaybeRequiresAPIKeyTests(TestCase):
    query = 'mutation { scheduleBuild(machine: "babette") }'

    def test_enabled(self, fixtures: Fixtures) -> None:
        with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_API_KEY_ENABLE": "yes"}):
            error = graphql(fixtures.client, self.query)["errors"][0]["message"]

        self.assertEqual(error, "Unauthorized to resolve scheduleBuild")

    def test_disabled(self, fixtures: Fixtures) -> None:
        with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_API_KEY_ENABLE": "no"}):
            response = graphql(fixtures.client, self.query)

        self.assertNotIn("errors", response)


def dummy_resolver(
    _obj: Any, _info: GraphQLResolveInfo, *args: Any, **kwargs: Any
) -> str:
    """Test resolver"""
    return "permitted"


@given("tmpdir", "publisher")
class RequireAPIKeyTestCase(TestCase):
    def test_good_apikey(self, fixtures: Fixtures) -> None:
        name = "test"
        api_key = ApiKey(
            name=name,
            key=apikey.create_api_key(),
            created=dt.datetime(2024, 4, 27, 20, 17, tzinfo=dt.UTC),
        )
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, api_key.key)
        gql_context = {"request": Mock(headers={"Authorization": f"Basic {encoded}"})}
        info = Mock(context=gql_context)
        info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        self.assertEqual(resolver(None, info), "permitted")

    def test_good_key_updates_records_last_use(self, fixtures: Fixtures) -> None:
        name = "test"
        api_key = ApiKey(
            name=name,
            key=apikey.create_api_key(),
            created=dt.datetime(2024, 4, 27, 20, 17, tzinfo=dt.UTC),
        )
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, api_key.key)
        gql_context = {"request": Mock(headers={"Authorization": f"Basic {encoded}"})}
        info = Mock(context=gql_context)
        info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        api_key = publisher.repo.api_keys.get(name)
        self.assertIs(api_key.last_used, None)

        resolver(None, info)

        api_key = publisher.repo.api_keys.get(name)
        self.assertIsNot(api_key.last_used, None, "The last_used field was not updated")

    def test_no_apikey(self, fixtures: Fixtures) -> None:
        gql_context = {"request": Mock(headers={})}
        info = Mock(context=gql_context)
        info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        with self.assertRaises(UnauthorizedError) as context:
            resolver(None, info)

        self.assertEqual(
            str(context.exception), "Unauthorized to resolve dummy_resolver"
        )

    def test_bad_apikey(self, fixtures: Fixtures) -> None:
        name = "test"
        api_key = ApiKey(
            name=name,
            key=apikey.create_api_key(),
            created=dt.datetime(2024, 4, 27, 20, 17, tzinfo=dt.UTC),
        )
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, "bogus")
        gql_context = {"request": Mock(headers={"Authorization": f"Basic {encoded}"})}
        info = Mock(context=gql_context)
        info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        with self.assertRaises(UnauthorizedError) as context:
            resolver(None, info)

        self.assertEqual(
            str(context.exception), "Unauthorized to resolve dummy_resolver"
        )


class LoadSchemaTests(TestCase):
    def test(self) -> None:
        schema = load_schema()

        self.assertEqual(schema, ([type_defs], resolvers))
