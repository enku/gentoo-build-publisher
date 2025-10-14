"""Type resolvers for the "Stats" type"""

# pylint: disable=missing-docstring

from typing import TypedDict

from ariadne import ObjectType
from graphql import GraphQLResolveInfo

from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.stats import Stats

type Info = GraphQLResolveInfo
BuildPublisherStats = ObjectType("BuildPublisherStats")


class PackageCount(TypedDict):
    machine: str
    count: int


@BuildPublisherStats.field("machineInfo")
def _(stats: Stats, _info: Info) -> list[MachineInfo]:
    return list(stats.machine_info.values())
