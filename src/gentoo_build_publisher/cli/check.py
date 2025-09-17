"""Check GBP storage and records"""

import argparse
import importlib.metadata
from typing import cast

from gbpcli.gbp import GBP
from gbpcli.types import Console

import gentoo_build_publisher.django._setup  # pylint: disable=unused-import
from gentoo_build_publisher.checks import Check
from gentoo_build_publisher.plugins import get_plugins

CHECK_GROUP = "gentoo_build_publisher.checks"


def parse_args(_parser: argparse.ArgumentParser) -> None:
    """We don't yet take arguments"""
    return


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """Check GBP storage and records"""
    total_errors = 0
    total_warnings = 0
    ep = importlib.metadata.EntryPoint

    for plugin in get_plugins():
        checks = plugin.checks or {}
        for name, value in checks.items():
            check_ep = ep(name=name, group=CHECK_GROUP, value=str(value))
            checker = cast(Check, check_ep.load())
            errors, warnings = checker(console)
            total_errors += errors
            total_warnings += warnings

    if total_errors:
        console.err.print("[warn]gbp check: Errors were encountered[/warn]")
    console.out.print(f"{total_errors} errors, {total_warnings} warnings")

    return total_errors
