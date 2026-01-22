"""Tests for graphql.utils"""

# pylint: disable=missing-docstring,unused-argument
from typing import Any
from unittest import mock

from graphql import GraphQLResolveInfo
from unittest_fixtures import Fixtures, given

import gbp_testkit.fixtures as testkit
from gbp_testkit import TestCase
from gbp_testkit.helpers import graphql, ts
from gentoo_build_publisher.cli import apikey
from gentoo_build_publisher.graphql import resolvers, type_defs
from gentoo_build_publisher.graphql.utils import (
    UnauthorizedError,
    load_schema,
    require_apikey,
)
from gentoo_build_publisher.types import ApiKey
from gentoo_build_publisher.utils import encode_basic_auth_data

from .lib import make_entry_point

Mock = mock.Mock


@given(testkit.tmpdir, testkit.publisher, testkit.client, testkit.environ)
class MaybeRequiresAPIKeyTests(TestCase):
    query = 'mutation { scheduleBuild(machine: "babette") }'

    def test_enabled(self, fixtures: Fixtures) -> None:
        environ = fixtures.environ
        environ["BUILD_PUBLISHER_API_KEY_ENABLE"] = "yes"

        error = graphql(fixtures.client, self.query)["errors"][0]["message"]

        self.assertEqual(error, "Unauthorized to resolve scheduleBuild")

    def test_disabled(self, fixtures: Fixtures) -> None:
        environ = fixtures.environ
        environ["BUILD_PUBLISHER_API_KEY_ENABLE"] = "no"

        response = graphql(fixtures.client, self.query)

        self.assertNotIn("errors", response)


def dummy_resolver(
    _obj: Any, _info: GraphQLResolveInfo, *args: Any, **kwargs: Any
) -> str:
    """Test resolver"""
    return "permitted"


def broken_resolver(
    _obj: Any, _info: GraphQLResolveInfo, *args: Any, **kwargs: Any
) -> str:
    """Test resolver"""
    raise ValueError()


@given(testkit.tmpdir, testkit.publisher, request=testkit.patch, info=testkit.patch)
class RequireAPIKeyTestCase(TestCase):
    def test_good_apikey(self, fixtures: Fixtures) -> None:
        name = "test"
        api_key = ApiKey(
            name=name, key=apikey.create_api_key(), created=ts("2024-04-27 20:17:00")
        )
        publisher = fixtures.publisher
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, api_key.key)
        fixtures.request.headers = {"Authorization": f"Basic {encoded}"}
        gql_context = {"request": fixtures.request}
        fixtures.info.context = gql_context
        fixtures.info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        self.assertEqual(resolver(None, fixtures.info), "permitted")
        assert fixtures.info.context["user"] == "test"

    def test_good_key_updates_records_last_use(self, fixtures: Fixtures) -> None:
        name = "test"
        api_key = ApiKey(
            name=name, key=apikey.create_api_key(), created=ts("2024-04-27 20:17:00")
        )
        publisher = fixtures.publisher
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, api_key.key)
        fixtures.request.headers = {"Authorization": f"Basic {encoded}"}
        gql_context = {"request": fixtures.request}
        fixtures.info.context = gql_context
        fixtures.info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        api_key = publisher.repo.api_keys.get(name)
        self.assertIs(api_key.last_used, None)

        resolver(None, fixtures.info)

        api_key = publisher.repo.api_keys.get(name)
        self.assertIsNot(api_key.last_used, None, "The last_used field was not updated")

    def test_no_apikey(self, fixtures: Fixtures) -> None:
        fixtures.request.headers = {}
        gql_context = {"request": fixtures.request}
        fixtures.info.context = gql_context
        fixtures.info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        with self.assertRaises(UnauthorizedError) as context:
            resolver(None, fixtures.info)

        self.assertEqual(
            str(context.exception), "Unauthorized to resolve dummy_resolver"
        )

    def test_bad_apikey(self, fixtures: Fixtures) -> None:
        name = "test"
        api_key = ApiKey(
            name=name, key=apikey.create_api_key(), created=ts("2024-04-27 20:17:00")
        )
        publisher = fixtures.publisher
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, "bogus")
        fixtures.request.headers = {"Authorization": f"Basic {encoded}"}
        gql_context = {"request": fixtures.request}
        fixtures.info.context = gql_context
        fixtures.info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        with self.assertRaises(UnauthorizedError) as context:
            resolver(None, fixtures.info)

        self.assertEqual(
            str(context.exception), "Unauthorized to resolve dummy_resolver"
        )

    def test_api_key_does_not_exist(self, fixtures: Fixtures) -> None:
        name = "test"
        encoded = encode_basic_auth_data(name, "bogus")
        fixtures.request.headers = {"Authorization": f"Basic {encoded}"}
        gql_context = {"request": fixtures.request}
        fixtures.info.context = gql_context
        fixtures.info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        with self.assertRaises(UnauthorizedError) as context:
            resolver(None, fixtures.info)

        self.assertEqual(
            str(context.exception), "Unauthorized to resolve dummy_resolver"
        )

    def test_other_error(self, fixtures: Fixtures) -> None:
        name = "test"
        api_key = ApiKey(
            name=name, key=apikey.create_api_key(), created=ts("2024-04-27 20:17:00")
        )
        publisher = fixtures.publisher
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, api_key.key)
        fixtures.request.headers = {"Authorization": f"Basic {encoded}"}
        gql_context = {"request": fixtures.request}
        fixtures.info.context = gql_context
        fixtures.info.path.key = "dummy_resolver"
        resolver = require_apikey(broken_resolver)

        with self.assertRaises(ValueError):
            resolver(None, fixtures.info)


@given(entry_points=testkit.patch)
class LoadSchemaTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        schema = load_schema()

        self.assertEqual(schema, ([type_defs], resolvers))

    @mock.patch("gentoo_build_publisher.plugins.entry_points")
    def test_with_plugin(
        self, plugins_entry_points: mock.Mock, fixtures: Fixtures
    ) -> None:
        ep = make_entry_point(
            "test",
            {
                "name": "test",
                "app": "test.apps.TestAppConfig",
                "graphql": "tests.mock_graphql_module",
            },
        )
        plugins_entry_points.return_value.select.return_value.__iter__.return_value = (
            iter([ep])
        )

        type_defs_, resolvers_ = load_schema()

        self.assertEqual(["This is a test"], type_defs_)
        self.assertEqual(["r1", "r2", "r3"], resolvers_)

    @mock.patch("gentoo_build_publisher.plugins.entry_points")
    def test_no_graphql(
        self, plugins_entry_points: mock.Mock, fixtures: Fixtures
    ) -> None:
        ep = make_entry_point(
            "test", {"name": "test", "app": "test.apps.TestAppConfig"}
        )
        plugins_entry_points.return_value.select.return_value.__iter__.return_value = (
            iter([ep])
        )
        type_defs_, resolvers_ = load_schema()

        self.assertEqual([], type_defs_)
        self.assertEqual([], resolvers_)
