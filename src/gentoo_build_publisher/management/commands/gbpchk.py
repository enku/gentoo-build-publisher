"""Check GBP storage/db"""
import itertools
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from gentoo_build_publisher.publisher import BuildPublisher, get_publisher
from gentoo_build_publisher.records import RecordNotFound
from gentoo_build_publisher.types import Build, Content


class Command(BaseCommand):
    """Command class for the gbpchk management command"""

    help = "Check GBP storage and records"

    def check_build_content(self, publisher: BuildPublisher) -> int:
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
                self.stderr.write(f"Path missing for {record}: {missing}")
                errors += 1

        return errors

    def check_orphans(self, publisher: BuildPublisher) -> int:
        """Check orphans (builds with no records)"""
        errors = 0

        for content in Content:
            directory = publisher.storage.root / content.value

            for path in directory.iterdir():
                if "." in path.name:
                    build = Build(path.name)

                    try:
                        publisher.records.get(build)
                    except RecordNotFound:
                        self.stderr.write(f"Record missing for {path}")
                        errors += 1
                elif path.is_symlink() and not path.exists():
                    self.stderr.write(f"Broken tag: {path}")
                    errors += 1

        return errors

    def check_inconsistent_tags(self, publisher: BuildPublisher) -> int:
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
                self.stderr.write(f'Tag "{tag}" has multiple targets: {targets}')
                errors += 1

        return errors

    def handle(self, *args: Any, **options: Any) -> None:
        publisher = get_publisher()

        errors = sum(
            (
                self.check_build_content(publisher),
                self.check_orphans(publisher),
                self.check_inconsistent_tags(publisher),
            )
        )

        if errors:
            self.stderr.write("Errors were encountered.")
            raise CommandError(errors)
