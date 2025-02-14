"""Resolvers for the MachineSummary GraphQL type"""

from typing import TypeAlias

from ariadne import ObjectType
from graphql import GraphQLResolveInfo

from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.types import Build

MachineSummaryType = ObjectType("MachineSummary")
Info: TypeAlias = GraphQLResolveInfo

# pylint: disable=missing-function-docstring


@MachineSummaryType.field("buildCount")
def build_count(machine_info: MachineInfo, _info: Info) -> int:
    return machine_info.build_count


@MachineSummaryType.field("latestBuild")
def latest_build(machine_info: MachineInfo, _info: Info) -> Build | None:
    return machine_info.latest_build


@MachineSummaryType.field("publishedBuild")
def published_build(machine_info: MachineInfo, _info: Info) -> Build | None:
    return machine_info.published_build
