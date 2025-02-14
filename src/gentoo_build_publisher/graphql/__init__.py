"""GraphQL resolvers for Gentoo Build Publisher"""

from __future__ import annotations

import importlib.metadata
from importlib import resources

import ariadne
from ariadne_django.scalars import datetime_scalar

from gentoo_build_publisher.types import ChangeState

from .build import BuildType
from .machine_summary import MachineSummaryType
from .mutations import Mutation
from .queries import Query

SCHEMA_GROUP = "gentoo_build_publisher.graphql_schema"
ChangeStateEnum = ariadne.EnumType("ChangeStateEnum", ChangeState)

type_defs = ariadne.gql(
    resources.read_text("gentoo_build_publisher.graphql", "schema.graphql")
)
resolvers = [
    BuildType,
    ChangeStateEnum,
    MachineSummaryType,
    Mutation,
    Query,
    datetime_scalar,
]


def load_schema() -> tuple[list[str], list[ariadne.ObjectType]]:
    """Load all GraphQL schema for Gentoo Build Publisher

    This function loads all entry points for the group
    "gentoo_build_publisher.graphql_schema" and returns them all into a single list.
    This list can be used to make_executable_schema()
    """
    all_type_defs: list[str] = []
    all_resolvers = []

    for entry_point in importlib.metadata.entry_points(group=SCHEMA_GROUP):
        module = entry_point.load()
        all_type_defs.append(module.type_defs)
        all_resolvers.extend(module.resolvers)

    return (all_type_defs, all_resolvers)


MERGED_TYPE_DEFS, MERGED_RESOLVERS = load_schema()
schema = ariadne.make_executable_schema(
    MERGED_TYPE_DEFS, *MERGED_RESOLVERS, ariadne.snake_case_fallback_resolvers
)
