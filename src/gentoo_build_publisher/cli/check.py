"""Check GBP storage and records"""
import argparse
import itertools
from pathlib import Path

import django
from gbpcli import GBP, Console

from gentoo_build_publisher.common import Build, Content
from gentoo_build_publisher.publisher import BuildPublisher, get_publisher
from gentoo_build_publisher.records import RecordNotFound


def parse_args(_parser: argparse.ArgumentParser) -> None:
    """We don't yet take arguments"""
    return


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """Check GBP storage and records"""
    django.setup()
    publisher = get_publisher()

    errors = sum(
        (
            check_build_content(publisher, console),
            check_orphans(publisher, console),
            check_inconsistent_tags(publisher, console),
        )
    )

    if errors:
        console.err.print("gbp check: Errors were encountered")

    return errors


def check_build_content(publisher: BuildPublisher, console: Console) -> int:
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
        for path in [
            publisher.storage.get_path(record, content) for content in Content
        ]:
            if not path.exists():
                missing.append(path)

        if missing:
            console.err.print(f"Path missing for {record}: {missing}")
            errors += 1

    return errors


def check_orphans(publisher: BuildPublisher, console: Console) -> int:
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
                    console.err.print(f"Record missing for {path}")
                    errors += 1
            elif path.is_symlink() and not path.exists():
                console.err.print(f"Broken tag: {path}")
                errors += 1

    return errors


def check_inconsistent_tags(publisher: BuildPublisher, console: Console) -> int:
    """Check for tags that have inconsistent targets"""
    errors = 0

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

    return errors