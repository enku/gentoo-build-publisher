"""The gbpcli stats subcommand"""

import argparse

from gbpcli.gbp import GBP
from gbpcli.types import Console

from gentoo_build_publisher.cache import cache
from gentoo_build_publisher.stats import Stats

HELP = "View/Clear the stats cache" ""
STATUS_CODE_UNKNOWN_ACTION = 255


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """View/Clear the stats cache"""
    match args.action:
        case "clear":
            return clear_action(args, console)
        case "collect":
            return collect_action(args, console)
        case "dump":
            return dump_action(args, console)

    console.err.print(f"Unknown action: {args.action}")
    return STATUS_CODE_UNKNOWN_ACTION


def parse_args(parser: argparse.ArgumentParser) -> None:
    """Set up parser arguments"""
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("clear", description="Clear the stats cache")
    subparsers.add_parser("collect", description="Collect stats and store in cache")
    subparsers.add_parser("dump", description="Show the stats cache")


def clear_action(_args: argparse.Namespace, _console: Console) -> int:
    """handle the "clear" action"""
    cache.delete("stats")

    return 0


def collect_action(_args: argparse.Namespace, _console: Console) -> int:
    """handle the "collect" action"""
    Stats.with_cache()

    return 0


def dump_action(_args: argparse.Namespace, console: Console) -> int:
    """handle the "dump" action"""
    stdout = console.out

    stdout.print(cache.get("stats"))

    return 0
