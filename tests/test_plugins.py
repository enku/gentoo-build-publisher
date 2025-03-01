# pylint: disable=missing-docstring
from unittest import TestCase, mock

from gentoo_build_publisher import plugins

from .helpers import make_entry_point

Plugin = plugins.Plugin


@mock.patch("gentoo_build_publisher.plugins.entry_points")
class GetPluginsTests(TestCase):
    def test_with_dict(self, m_entry_points: mock.Mock) -> None:
        ep = make_entry_point(
            "foo", {"name": "test", "app": "test.apps.TestAppConfig", "throw": "away"}
        )
        entry_points = m_entry_points.return_value
        entry_points.select.return_value.__iter__.side_effect = (iter([]), iter([ep]))

        result = plugins.get_plugins()

        plugin = Plugin(
            name="test", app="test.apps.TestAppConfig", graphql=None, urls=None
        )
        self.assertEqual([plugin], result)
        entry_points.select.assert_any_call(group="gentoo_build_publisher.apps")
        entry_points.select.assert_any_call(group="gentoo_build_publisher.plugins")

    def test_with_string(self, m_entry_points: mock.Mock) -> None:
        ep = make_entry_point("test", "test.apps.TestAppConfig")
        entry_points = m_entry_points.return_value
        entry_points.select.return_value.__iter__.side_effect = (iter([ep]), iter([]))

        result = plugins.get_plugins()

        plugin = Plugin(
            name="test",
            app="test.apps.TestAppConfig",
            graphql=None,
            urls="test.apps.TestAppConfig.urls",
        )
        self.assertEqual([plugin], result)
        entry_points.select.assert_any_call(group="gentoo_build_publisher.apps")
        entry_points.select.assert_any_call(group="gentoo_build_publisher.plugins")
