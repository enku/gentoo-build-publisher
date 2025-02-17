"""Utilities for dumping/restoring builds"""

import tarfile as tar
import tempfile
from typing import IO, Iterable

from gentoo_build_publisher import publisher
from gentoo_build_publisher.types import Build, DumpCallback, default_dump_callback

from . import records, storage


def dump(
    builds: Iterable[Build],
    outfile: IO[bytes],
    *,
    callback: DumpCallback = default_dump_callback,
) -> None:
    """Dump the given builds to the given outfile"""
    builds = list(builds)
    builds.sort(key=lambda build: (build.machine, build.build_id))

    with tar.open(fileobj=outfile, mode="w|") as tarfile:
        # first dump records
        with tempfile.SpooledTemporaryFile(mode="w+b") as tmp:
            my_records = [publisher.repo.build_records.get(build) for build in builds]
            records.dump(my_records, tmp, callback=callback)
            tmp.seek(0)
            tarinfo = tarfile.gettarinfo(arcname="records.json", fileobj=tmp)
            tarfile.addfile(tarinfo, tmp)

        # then dump storage
        with tempfile.TemporaryFile(mode="w+b") as tmp:
            storage.dump(builds, tmp, callback=callback)
            tmp.seek(0)
            tarinfo = tarfile.gettarinfo(arcname="storage.tar", fileobj=tmp)
            tarfile.addfile(tarinfo, tmp)


def restore(
    infile: IO[bytes], *, callback: DumpCallback = default_dump_callback
) -> None:
    """Restore builds from the given infile"""
    with tar.open(fileobj=infile, mode="r|") as tarfile:
        for member in tarfile:
            if member.name == "records.json":
                records_dump = tarfile.extractfile(member)
                assert records_dump is not None
                records.restore(records_dump, callback=callback)
                continue
            if member.name == "storage.tar":
                storage_dump = tarfile.extractfile(member)
                assert storage_dump is not None
                storage.restore(storage_dump, callback=callback)
                continue
