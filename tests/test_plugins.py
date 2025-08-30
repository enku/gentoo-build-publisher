# pylint: disable=missing-docstring
from unittest import TestCase

from unittest_fixtures import Fixtures, given, where

import gbp_testkit.fixtures as testkit
from gentoo_build_publisher import plugins

from .lib import make_entry_point

Plugin = plugins.Plugin


@given(entry_points=testkit.patch)
@where(entry_points__target="gentoo_build_publisher.plugins.entry_points")
class GetPluginsTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        ep = make_entry_point(
            "foo", {"name": "test", "app": "test.apps.TestAppConfig", "throw": "away"}
        )
        entry_points = fixtures.entry_points.return_value
        entry_points.select.return_value.__iter__.return_value = iter([ep])

        result = plugins.get_plugins()

        plugin = Plugin(
            name="test", app="test.apps.TestAppConfig", graphql=None, urls=None
        )
        self.assertEqual([plugin], result)
        entry_points.select.assert_any_call(group="gentoo_build_publisher.plugins")

    def test_priority(self, fixtures: Fixtures) -> None:
        a = make_entry_point("foo", {"name": "foo", "app": "test.apps.TestAppConfig"})
        b = make_entry_point(
            "bar", {"name": "bar", "app": "test.apps.TestAppConfig", "priority": -10}
        )
        entry_points = fixtures.entry_points.return_value
        entry_points.select.return_value.__iter__.return_value = iter([a, b])

        result = plugins.get_plugins()

        self.assertEqual(["bar", "foo"], [i.name for i in result])
