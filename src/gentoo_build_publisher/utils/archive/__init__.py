"""Utilities for dumping/restoring builds"""

import datetime as dt
import io
import tarfile as tar
import tempfile
from typing import IO, Iterable

from gentoo_build_publisher import publisher
from gentoo_build_publisher.types import Build, DumpCallback, default_dump_callback
from gentoo_build_publisher.utils import time

from . import metadata, records, storage

METADATA_NAME = "gbp-archive"


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
        fp: IO[bytes]

        # first add the metadata
        with io.BytesIO() as fp:
            my_metadata = metadata.create(builds, time.localtime())
            metadata.dump(my_metadata, fp, callback=callback)
            fp.seek(0)
            tarinfo = bytes_io_to_tarinfo(METADATA_NAME, fp)
            tarfile.addfile(tarinfo, fp)

        # then dump records
        with tempfile.SpooledTemporaryFile(mode="w+b") as fp:
            my_records = [publisher.repo.build_records.get(build) for build in builds]
            records.dump(my_records, fp, callback=callback)
            fp.seek(0)
            tarinfo = tarfile.gettarinfo(arcname="records.json", fileobj=fp)
            tarfile.addfile(tarinfo, fp)

        # then dump storage
        with tempfile.TemporaryFile(mode="w+b") as fp:
            storage.dump(builds, fp, callback=callback)
            fp.seek(0)
            tarinfo = tarfile.gettarinfo(arcname="storage.tar", fileobj=fp)
            tarfile.addfile(tarinfo, fp)


def restore(
    infile: IO[bytes], *, callback: DumpCallback = default_dump_callback
) -> None:
    """Restore builds from the given infile"""
    with tar.open(fileobj=infile, mode="r|") as tarfile:
        # First restore the metadata. Currently nothing is done with it
        member = tarfile.next()
        assert member is not None
        fp = tarfile.extractfile(member)
        assert fp is not None
        metadata.restore(fp, callback=callback)

        # Then restore the records
        member = tarfile.next()
        assert member is not None
        fp = tarfile.extractfile(member)
        assert fp is not None
        records.restore(fp, callback=callback)

        # Then restore the storage
        member = tarfile.next()
        assert member is not None
        fp = tarfile.extractfile(member)
        assert fp is not None
        storage.restore(fp, callback=callback)


def bytes_io_to_tarinfo(
    arcname: str, fp: io.BytesIO, mode: int = 0o0644, mtime: int | None = None
) -> tar.TarInfo:
    """Return a TarInfo given BytesIO and archive name"""
    tarinfo = tar.TarInfo(arcname)
    tarinfo.size = len(fp.getvalue())
    tarinfo.mode = mode
    tarinfo.mtime = (
        mtime if mtime is not None else int(dt.datetime.utcnow().timestamp())
    )

    return tarinfo
