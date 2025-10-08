"""Resolvers for the MachineSummary GraphQL type"""

# pylint: disable=missing-function-docstring

from ariadne import ObjectType
from graphql import GraphQLResolveInfo

from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.stats import Stats
from gentoo_build_publisher.types import Build

type Info = GraphQLResolveInfo

MachineSummary = ObjectType("MachineSummary")


@MachineSummary.field("buildCount")
def _(machine_info: MachineInfo, _info: Info) -> int:
    return machine_info.build_count


@MachineSummary.field("latestBuild")
def _(machine_info: MachineInfo, _info: Info) -> Build | None:
    return machine_info.latest_build


@MachineSummary.field("publishedBuild")
def _(machine_info: MachineInfo, _info: Info) -> Build | None:
    return machine_info.published_build


@MachineSummary.field("packageCount")
def _(machine_info: MachineInfo, _info: Info) -> int:
    machine = machine_info.machine
    stats = Stats.with_cache()

    return stats.package_counts[machine]
