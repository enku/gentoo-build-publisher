"""Type resolvers for the "Stats" type"""

# pylint: disable=missing-docstring

from typing import TypedDict

from ariadne import ObjectType
from graphql import GraphQLResolveInfo

from gentoo_build_publisher.stats import MachineInfoDataClass, Stats

type Info = GraphQLResolveInfo
BUILD_PUBLISHER_STATS = ObjectType("BuildPublisherStats")


class PackageCount(TypedDict):
    machine: str
    count: int


@BUILD_PUBLISHER_STATS.field("machineInfo")
def machine_info(stats: Stats, _info: Info) -> list[MachineInfoDataClass]:
    return list(stats.machine_info.values())
