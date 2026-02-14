"""GraphQL resolvers for Gentoo Build Publisher"""

from importlib import resources

import ariadne

from gentoo_build_publisher.types import ChangeState

from .build import BUILD, PACKAGE
from .machine_summary import MACHINE_SUMMARY
from .mutations import MUTATION
from .queries import QUERY, TAG_INFO
from .scalars import date_scalar, datetime_scalar
from .stats import BUILD_PUBLISHER_STATS
from .utils import load_schema

CHANGE_STATE_ENUM = ariadne.EnumType("ChangeStateEnum", ChangeState)

type_defs = ariadne.gql(
    resources.read_text("gentoo_build_publisher.graphql", "schema.graphql")
)
resolvers = [
    BUILD_PUBLISHER_STATS,
    BUILD,
    CHANGE_STATE_ENUM,
    MACHINE_SUMMARY,
    MUTATION,
    PACKAGE,
    QUERY,
    TAG_INFO,
    date_scalar,
    datetime_scalar,
]


MERGED_TYPE_DEFS, MERGED_RESOLVERS = load_schema()
schema = ariadne.make_executable_schema(
    MERGED_TYPE_DEFS, *MERGED_RESOLVERS, ariadne.snake_case_fallback_resolvers
)
