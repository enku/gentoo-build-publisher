"""utilities for archiving Storage"""

import tarfile as tar
from typing import IO, Iterable

from gentoo_build_publisher import fs, publisher
from gentoo_build_publisher.types import Build, Content, DumpCallback


def dump(builds: Iterable[Build], fp: IO[bytes], *, callback: DumpCallback) -> None:
    """Dump the given builds' storage into the given tarfile"""
    storage = publisher.storage

    with tar.open(fileobj=fp, mode="w|") as tarfile, fs.cd(storage.root):
        for build in builds:
            callback("dump", "storage", build)
            for content in Content:
                for tag in [None, *storage.get_tags(build)]:
                    path = storage.get_path(build, content, tag=tag)
                    path = path.relative_to(storage.root)
                    tarfile.add(path)


def restore(fp: IO[bytes], *, callback: DumpCallback) -> list[Build]:
    """Restore builds from the given file object

    This is the complement of dump()
    Return the list of builds restored.
    """
    storage = publisher.storage
    restore_list: list[Build] = []

    with tar.open(fileobj=fp, mode="r|") as tarfile, fs.cd(storage.root):
        for member in tarfile:
            if is_content_dir(member, Content.REPOS):
                build = Build.from_id(member.name.split("/", 1)[1])
                restore_list.append(build)
                callback("restore", "storage", build)
            tarfile.extract(member)

    return restore_list


def is_content_dir(member: tar.TarInfo, content_type: Content) -> bool:
    """Return true if the given TarFile member is a repo directory"""
    if not member.isdir():
        return False

    parts = member.name.split("/")

    return len(parts) == 2 and parts[0] == content_type.value
