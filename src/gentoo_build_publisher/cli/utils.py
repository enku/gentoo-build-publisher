"""Utilities for the cli subcommands"""

from typing import cast

from gbpcli.gbp import GBP
from gbpcli.graphql import Query


def get_dist_query(
    name: str, gbp: GBP, distribution: str = "gentoo_build_publisher"
) -> Query:
    """Return the Query with the given name"""
    return cast(Query, getattr(getattr(gbp.query, distribution), name))
