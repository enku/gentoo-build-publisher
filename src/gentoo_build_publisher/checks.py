"""Gentoo Build Publisher Checks"""

import itertools
import json
from pathlib import Path
from typing import Callable, TypeAlias

from gbpcli.types import Console

from gentoo_build_publisher import publisher
from gentoo_build_publisher.records import RecordNotFound
from gentoo_build_publisher.types import Build, Content

CheckResult: TypeAlias = tuple[int, int]
Check: TypeAlias = Callable[[Console], CheckResult]


def build_content(console: Console) -> CheckResult:
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


def orphans(console: Console) -> CheckResult:
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


def inconsistent_tags(console: Console) -> CheckResult:
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


def dirty_temp(console: Console) -> CheckResult:
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


def corrupt_gbp_json(console: Console) -> CheckResult:
    """Check that the gbp.json file is not corrupt"""
    errors = 0
    warnings = 0

    machines = publisher.repo.build_records.list_machines()
    records = itertools.chain(
        *(publisher.repo.build_records.for_machine(machine) for machine in machines)
    )
    storage = publisher.storage

    for record in records:
        gbp_json_path = storage.get_path(record, Content.BINPKGS) / "gbp.json"

        if not gbp_json_path.exists():
            # This is a warning and not an error because early versions of GBP did not
            # create a gbp.json. But that's old behavior and I want to eventually phase
            # this out and make it an error. Would be nice to conditionally make this
            # check based on what version of GBP created the build (ironically the
            # version is stored in gbp.json).
            console.err.print(f"Warning: {gbp_json_path} is missing.")
            warnings += 1
            continue

        with gbp_json_path.open("rb") as gbp_json:
            try:
                json.load(gbp_json)
            except (UnicodeDecodeError, json.JSONDecodeError):
                console.err.print(f"Error: {gbp_json_path} is corrupt.")
                errors += 1

    return errors, warnings
