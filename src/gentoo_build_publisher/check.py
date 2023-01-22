"Check GBP storage and records"
import argparse
import itertools
import sys
from pathlib import Path
from typing import TextIO

import django
from gbpcli import GBP
from rich.console import Console

from gentoo_build_publisher.publisher import BuildPublisher, get_publisher
from gentoo_build_publisher.types import Build, Content, RecordNotFound


def parse_args(_parser: argparse.ArgumentParser) -> None:
    """We don't yet take arguments"""
    return


def handler(
    args: argparse.Namespace, _gbp: GBP, _console: Console, errorf: TextIO = sys.stderr
) -> int:
    """Check GBP storage and records"""
    django.setup()
    publisher = get_publisher()

    errors = sum(
        (
            check_build_content(publisher, errorf),
            check_orphans(publisher, errorf),
            check_inconsistent_tags(publisher, errorf),
        )
    )

    if errors:
        print("gbp check: Errors were encountered", file=errorf)

    return errors


def check_build_content(publisher: BuildPublisher, errorf: TextIO) -> int:
    """Check build content"""
    errors = 0

    machines = publisher.records.list_machines()
    records = itertools.chain(
        *(publisher.records.for_machine(machine) for machine in machines)
    )

    for record in records:
        if not record.completed:
            continue

        missing: list[Path] = []
        for content in Content:
            path = publisher.storage.get_path(record, content)

            if not path.exists():
                missing.append(path)

        if missing:
            print(f"Path missing for {record}: {missing}", file=errorf)
            errors += 1

    return errors


def check_orphans(publisher: BuildPublisher, errorf: TextIO) -> int:
    """Check orphans (builds with no records)"""
    errors = 0

    for content in Content:
        directory = publisher.storage.root / content.value

        for path in directory.iterdir():
            if "." in path.name:
                build = Build(*path.name.split(".", 1))

                try:
                    publisher.records.get(build)
                except RecordNotFound:
                    print(f"Record missing for {path}", file=errorf)
                    errors += 1
            elif path.is_symlink() and not path.exists():
                print(f"Broken tag: {path}", file=errorf)
                errors += 1

    return errors


def check_inconsistent_tags(publisher: BuildPublisher, errorf: TextIO) -> int:
    """Check for tags that have inconsistent targets"""
    errors = 0

    tags: dict[str, set[str]] = {}

    for content in Content:
        path = publisher.storage.root / content.value
        for item in path.iterdir():
            if not item.is_symlink():
                continue

            tag = item.name

            if tag not in tags:
                tags[tag] = set()

            build = item.resolve().name

            tags[tag].add(build)

    for tag, targets in tags.items():
        if len(targets) != 1:
            print(f'Tag "{tag}" has multiple targets: {targets}', file=errorf)
            errors += 1

    return errors
