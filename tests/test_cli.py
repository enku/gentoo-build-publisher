# pylint: disable=missing-docstring
import importlib.resources
from unittest import mock

from gbpcli.graphql import Query

from gentoo_build_publisher.cli import get_dist_query

from . import TestCase, test_gbp

CREATE_MACHINE_QUERY_STR = (
    importlib.resources.files("gentoo_build_publisher") / "queries/create_repo.graphql"
).read_text(encoding="UTF-8")


class GetDistQueryTests(TestCase):
    """Tests for the get_dist_query helper"""

    def test_old_world(self) -> None:
        # Pre gbpcli-2.0
        gbp = test_gbp("http://test.invalid/")
        query = get_dist_query(
            "create_repo", gbp, distribution="gentoo_build_publisher"
        )

        self.assertEqual(str(query), CREATE_MACHINE_QUERY_STR)

    def test_new_world(self) -> None:
        # post gbpcli-2.0. Not yet released so we mock the expected behavior
        gbp = mock.MagicMock()
        del gbp.query._distribution
        gbp.query.gentoo_build_publisher.create_repo = Query(
            CREATE_MACHINE_QUERY_STR, "http://test.invalid", mock.Mock()
        )
        query = get_dist_query(
            "create_repo", gbp, distribution="gentoo_build_publisher"
        )

        self.assertEqual(str(query), CREATE_MACHINE_QUERY_STR)
