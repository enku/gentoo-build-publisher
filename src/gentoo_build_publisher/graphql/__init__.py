"""GraphQL resolvers for Gentoo Build Publisher"""

from importlib import resources

import ariadne

from gentoo_build_publisher.types import ChangeState

from .build import BuildType
from .machine_summary import MachineSummary
from .mutations import Mutation
from .queries import Query
from .scalars import datetime_scalar
from .utils import load_schema

ChangeStateEnum = ariadne.EnumType("ChangeStateEnum", ChangeState)

type_defs = ariadne.gql(
    resources.read_text("gentoo_build_publisher.graphql", "schema.graphql")
)
resolvers = [
    BuildType,
    ChangeStateEnum,
    MachineSummary,
    Mutation,
    Query,
    datetime_scalar,
]


MERGED_TYPE_DEFS, MERGED_RESOLVERS = load_schema()
schema = ariadne.make_executable_schema(
    MERGED_TYPE_DEFS, *MERGED_RESOLVERS, ariadne.snake_case_fallback_resolvers
)
