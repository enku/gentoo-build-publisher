"""Gentoo Build Publisher-specific gbpcli subcommands"""

from typing import cast

from gbpcli import GBP
from gbpcli.graphql import Query


def get_dist_query(
    name: str, gbp: GBP, distribution: str = "gentoo_build_publisher"
) -> Query:
    """Return the Query with the given name"""
    return cast(Query, getattr(getattr(gbp.query, distribution), name))
