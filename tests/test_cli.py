# pylint: disable=missing-docstring
import importlib.resources
from unittest import mock

from gbpcli.graphql import Query

from gbp_testkit import TestCase
from gbp_testkit.helpers import test_gbp
from gentoo_build_publisher.cli.utils import get_dist_query

CREATE_MACHINE_QUERY_STR = (
    importlib.resources.files("gentoo_build_publisher") / "queries/create_repo.graphql"
).read_text(encoding="UTF-8")


class GetDistQueryTests(TestCase):
    """Tests for the get_dist_query helper"""

    def test(self) -> None:
        gbp = test_gbp("http://test.invalid/")
        gbp.query.gentoo_build_publisher.create_repo = Query(
            CREATE_MACHINE_QUERY_STR, "http://test.invalid", mock.Mock()
        )
        query = get_dist_query(
            "create_repo", gbp, distribution="gentoo_build_publisher"
        )

        self.assertEqual(str(query), CREATE_MACHINE_QUERY_STR)
