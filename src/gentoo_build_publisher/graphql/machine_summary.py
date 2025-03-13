"""Resolvers for the MachineSummary GraphQL type"""

from typing import TypeAlias

from ariadne import ObjectType
from graphql import GraphQLResolveInfo

from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.types import Build

MachineSummary = ObjectType("MachineSummary")
Info: TypeAlias = GraphQLResolveInfo

# pylint: disable=missing-function-docstring


@MachineSummary.field("buildCount")
def _(machine_info: MachineInfo, _info: Info) -> int:
    return machine_info.build_count


@MachineSummary.field("latestBuild")
def _(machine_info: MachineInfo, _info: Info) -> Build | None:
    return machine_info.latest_build


@MachineSummary.field("publishedBuild")
def _(machine_info: MachineInfo, _info: Info) -> Build | None:
    return machine_info.published_build
