"""Dump builds to a file"""

import argparse

from gbpcli.gbp import GBP
from gbpcli.types import Console

from gentoo_build_publisher import publisher
from gentoo_build_publisher.records import BuildRecord

HELP = "Dump builds to a file"


class BuildSpecLookupError(LookupError):
    """The buildspec wasn't found in the Build Records"""


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """Dump builds to a file"""
    try:
        builds = builds_to_dump(args.machines)
    except BuildSpecLookupError as error:
        console.err.print(f"{error.args[0]} not found.")
        return 1

    with open(args.filename, "wb") as fp:
        publisher.dump(builds, fp)

    return 0


def parse_args(parser: argparse.ArgumentParser) -> None:
    """Set subcommand arguments"""
    parser.add_argument("filename", help="Filename to dump builds to")
    parser.add_argument("machines", nargs="*", help="machine(s) to dump")


def builds_to_dump(buildspecs: list[str]) -> set[BuildRecord]:
    """Return the set of builds to be dumped according to the given buildspecs"""
    records = publisher.repo.build_records
    all_builds = {
        build
        for machine in records.list_machines()
        for build in records.for_machine(machine)
    }
    if not buildspecs:
        return all_builds

    to_backup: set[BuildRecord] = set()

    for buildspec in buildspecs:
        to_backup.update(builds_from_spec(buildspec, all_builds))

    return to_backup


def builds_from_spec(buildspec: str, builds: set[BuildRecord]) -> set[BuildRecord]:
    """Return the set of BuildRecords matching the given buildspec

    buildspec can be:

        - <machine> Returns all the builds for the given machine
        - <machine>.<build_id> Returns the given build

    If the given machine or build doesn't exist in the build records,
    BuildSpecLookupError is raised.
    """
    subset: set[BuildRecord] = set()
    machine, _, build_id = buildspec.partition(".")

    if build_id:
        if bs := {b for b in builds if b.machine == machine and b.build_id == build_id}:
            subset.update(bs)
        else:
            raise BuildSpecLookupError(buildspec)
    else:
        if bs := {b for b in builds if b.machine == machine}:
            subset.update(bs)
        else:
            raise BuildSpecLookupError(buildspec)
    return subset
