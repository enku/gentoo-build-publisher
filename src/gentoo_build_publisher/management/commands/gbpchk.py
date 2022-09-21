"""Check GBP storage/db"""
import itertools
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from gentoo_build_publisher.publisher import get_publisher
from gentoo_build_publisher.records import RecordNotFound
from gentoo_build_publisher.types import Build, Content


class Command(BaseCommand):
    """Command class for the gbpchk management command"""

    help = "Check GBP storage and records"

    def handle(self, *args: Any, **options: Any) -> None:
        errors = 0
        publisher = get_publisher()

        # Pass 1: check build content
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

        # Pass 2: check for orphans and dangling tags
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

        if errors:
            self.stderr.write("Errors were encountered.")
            raise CommandError(errors)
