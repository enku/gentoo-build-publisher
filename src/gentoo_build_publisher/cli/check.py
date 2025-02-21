"""Check GBP storage and records"""

import argparse
import itertools
from pathlib import Path
from typing import Callable, TypeAlias

from gbpcli.gbp import GBP
from gbpcli.types import Console

import gentoo_build_publisher._django_setup  # pylint: disable=unused-import
from gentoo_build_publisher import publisher
from gentoo_build_publisher.records import RecordNotFound
from gentoo_build_publisher.types import Build, Content

CheckResult: TypeAlias = tuple[int, int]
Check: TypeAlias = Callable[[Console], CheckResult]

_CHECK_REGISTRY: list[Check] = []


def register(func: Check) -> Check:
    """Register a check"""
    _CHECK_REGISTRY.append(func)
    return func


def parse_args(_parser: argparse.ArgumentParser) -> None:
    """We don't yet take arguments"""
    return


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """Check GBP storage and records"""
    total_errors = 0
    total_warnings = 0

    for checker in _CHECK_REGISTRY:
        errors, warnings = checker(console)
        total_errors += errors
        total_warnings += warnings

    if total_errors:
        console.err.print("[warn]gbp check: Errors were encountered[/warn]")
    console.out.print(f"{total_errors} errors, {total_warnings} warnings")

    return total_errors


@register
def check_build_content(console: Console) -> CheckResult:
    """Check build content"""
    errors = 0
    warnings = 0

    machines = publisher.repo.build_records.list_machines()
    records = itertools.chain(
        *(publisher.repo.build_records.for_machine(machine) for machine in machines)
    )

    for record in records:
        missing: list[Path] = []
        for path in [
            publisher.storage.get_path(record, content) for content in Content
        ]:
            if not path.exists():
                missing.append(path)

        if missing:
            console.err.print(f"Path missing for {record}: {missing}")
            if record.completed:
                errors += 1
            else:
                warnings += 1

    return errors, warnings


@register
def check_orphans(console: Console) -> CheckResult:
    """Check orphans (builds with no records)"""
    errors = 0
    warnings = 0

    for content in Content:
        directory = publisher.storage.root / content.value

        for path in directory.iterdir():
            if "." in path.name and not path.is_symlink():
                build = Build(*path.name.split(".", 1))

                try:
                    publisher.repo.build_records.get(build)
                except RecordNotFound:
                    console.err.print(f"Record missing for {path}")
                    errors += 1
            elif path.is_symlink() and not path.exists():
                console.err.print(f"Broken tag: {path}")
                errors += 1

    return errors, warnings


@register
def check_inconsistent_tags(console: Console) -> CheckResult:
    """Check for tags that have inconsistent targets"""
    errors = 0
    warnings = 0

    tags: dict[str, set[str]] = {}

    for path in [publisher.storage.root / content.value for content in Content]:
        for item in path.iterdir():
            if not item.is_symlink():
                continue

            if (tag := item.name) not in tags:
                tags[tag] = set()

            build = item.resolve().name

            tags[tag].add(build)

    for tag, targets in tags.items():
        if len(targets) != 1:
            console.err.print(f'Tag "{tag}" has multiple targets: {targets}')
            errors += 1

    return errors, warnings


@register
def check_dirty_temp(console: Console) -> CheckResult:
    """Warn if the temp dir is not empty"""
    errors = 0
    warnings = 0
    storage = publisher.storage
    root = storage.root
    tmp = root / "tmp"

    if next(tmp.iterdir(), None):
        warnings += 1
        console.err.print(f"Warning: {tmp} is not empty.")

    return errors, warnings
