"""Utilities for restoring gbp dumps"""

import datetime as dt
import json
from dataclasses import asdict
from typing import IO, Iterable

from gentoo_build_publisher import publisher
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import DumpCallback
from gentoo_build_publisher.utils import convert_to, decode_to, serializable


def dump(
    builds: Iterable[BuildRecord], outfile: IO[bytes], *, callback: DumpCallback
) -> None:
    """Dump the given builds as JSON to the given file"""
    for build in (builds := list(builds)):
        callback("dump", "records", build)

    build_list = [asdict(build) for build in builds]

    serialized = json.dumps(build_list, default=serializable)
    outfile.write(serialized.encode("utf8"))


def restore(infile: IO[bytes], *, callback: DumpCallback) -> list[BuildRecord]:
    """Restore the JSON given in the infile to BuildRecords in the given RecordDB

    Return the restored records
    """
    restore_list: list[BuildRecord] = []

    items = json.load(infile)
    for item in items:
        record = decode_to(BuildRecord, item)
        callback("restore", "records", record)
        record = publisher.repo.build_records.save(record)
        restore_list.append(record)

    return restore_list


@convert_to(BuildRecord, "built")
@convert_to(BuildRecord, "completed")
@convert_to(BuildRecord, "submitted")
def _(value: str | None) -> dt.datetime | None:
    return None if value is None else dt.datetime.fromisoformat(value)
