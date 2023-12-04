"""Gentoo Build Publisher-specific gbpcli subcommands"""
from typing import cast

from gbpcli import GBP
from gbpcli.graphql import Query


def get_dist_query(
    name: str, gbp: GBP, distribution: str = "gentoo_build_publisher"
) -> Query:
    """Return the Query with the given name

    This function has a side-effect on pre 2.0 versions of gbpcli in that it mutates the
    gbp argument to point to the given distribution's query database.
    """
    if hasattr(gbp.query, "_distribution"):
        # Older GBP can only see the queries for the "gbpcli" distribution and need to
        # be overridden to see queries from other distributions
        gbp.query._distribution = distribution  # pylint: disable=protected-access
        return cast(Query, getattr(gbp.query, name))

    return cast(Query, getattr(getattr(gbp.query, distribution), name))
