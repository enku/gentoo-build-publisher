"""Resolvers for the MachineSummary GraphQL type"""

# pylint: disable=missing-docstring
import datetime as dt
from typing import Any, TypedDict

from ariadne import ObjectType
from graphql import GraphQLResolveInfo

from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.stats import Stats
from gentoo_build_publisher.types import Build, Package

type Info = GraphQLResolveInfo

MachineSummary = ObjectType("MachineSummary")


class DaysPackages(TypedDict):
    date: dt.date
    packages: list[Package]


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


@MachineSummary.field("packagesByDay")
def _(machine_info: MachineInfo, _info: Info) -> list[DaysPackages]:
    machine = machine_info.machine
    stats = Stats.with_cache()
    packages_by_day = stats.packages_by_day[machine]

    return [
        {"date": date, "packages": sorted(packages, key=lambda p: p.cpv)}
        for date, packages in packages_by_day.items()
    ]


@MachineSummary.field("totalPackageSize")
def _(machine_info: MachineInfo, _info: Info) -> str:
    machine = machine_info.machine
    stats = Stats.with_cache()

    return str(stats.total_package_size.get(machine, 0))


@MachineSummary.field("tagInfo")
def _(machine_info: MachineInfo, _info: Info) -> list[dict[str, Any]]:
    machine = machine_info.machine
    tags = machine_info.tags

    return [{"tag": tag, "build": None, "machine": machine} for tag in tags]
