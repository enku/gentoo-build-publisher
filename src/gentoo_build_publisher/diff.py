"""Library to show differences between directories

This is made to calculate differences between binpkg directories but can be used for any
similar purpose.
"""
import filecmp
import os
from dataclasses import dataclass
from enum import Enum
from typing import Generator


class Status(Enum):
    """Change item status (added, changed, removed)"""

    REMOVED = -1
    CHANGED = 0
    ADDED = 1

    def is_a_build(self):
        """Return true if this is a "build" change"""
        return self is not Status.REMOVED


@dataclass(frozen=True)
class Change:
    """A changed item (file or directory)"""

    item: str
    status: Status

    def tuple(self) -> tuple[int, str]:
        """Return Change as a JSON-compatible tuple"""
        return (self.status.value, self.item)


HAS_REMOVEPREFIX = hasattr(str, "removeprefix")
HAS_REMOVESUFFIX = hasattr(str, "removesuffix")


def removeprefix(string: str, prefix: str) -> str:
    """Implementation of Python 3.9's str.removeprefix"""
    if HAS_REMOVEPREFIX:
        return string.removeprefix(prefix)

    if string.startswith(prefix):
        return string[len(prefix) :]

    return string


def removesuffix(string: str, suffix: str) -> str:
    """Implementation of Python 3.9's str.removesuffix"""
    if HAS_REMOVESUFFIX:
        return string.removesuffix(suffix)

    if string.endswith(suffix):
        return string[: -len(suffix)]

    return string


def path_to_pkg(prefix: str, path: str) -> str:
    """Return the binpkg name given the path"""
    stripped = removesuffix(
        removesuffix(removeprefix(removeprefix(path, prefix), "/"), ".xpak"), ".tbz2"
    )

    category, _, package = stripped.split("/")

    return f"{category}/{package}"


def changes(
    left: str, right: str, dircmp: filecmp.dircmp
) -> Generator[Change, None, None]:
    """Recursive generator for file comparisions"""
    for subcmp in dircmp.subdirs.values():

        for item in subcmp.left_only:
            path = f"{subcmp.left}/{item}"

            if os.path.isdir(path):
                yield from subtree(left, path, Status.REMOVED)
                continue

            yield Change(item=path_to_pkg(left, path), status=Status.REMOVED)

        for item in subcmp.right_only:
            path = f"{subcmp.right}/{item}"

            if os.path.isdir(path):
                yield from subtree(right, path, Status.ADDED)
                continue

            yield Change(item=path_to_pkg(right, path), status=Status.ADDED)

        for item in subcmp.diff_files:
            path1 = f"{subcmp.left}/{item}"
            path2 = f"{subcmp.right}/{item}"

            if os.path.isdir(path1) and os.path.isdir(path2):
                yield from subtree(left, path1, Status.REMOVED)
                yield from subtree(right, path2, Status.ADDED)
                continue

            yield Change(item=path_to_pkg(left, path1), status=Status.CHANGED)
            yield Change(item=path_to_pkg(right, path2), status=Status.CHANGED)

        yield from changes(left, right, subcmp)


def subtree(root: str, path: str, status: Status) -> Generator[Change, None, None]:
    """Yield an entire subtree as added or removed"""
    for dirpath, _, filenames in os.walk(path):
        for filename in filenames:
            path = os.path.join(dirpath, filename)

            yield Change(path_to_pkg(root, path), status=status)


def dirdiff(left: str, right: str) -> Generator[Change, None, None]:
    """Generate differences between to directory paths"""
    dircmp = filecmp.dircmp(left, right)

    yield from changes(left, right, dircmp)


def diff_notes(left: str, right: str, header: str = "") -> str:
    """Return dirdiff as a string of notes

    If there are no changes, return an empty string
    """
    changeset = list(set(i for i in dirdiff(left, right) if i.status.is_a_build()))
    changeset.sort(key=lambda i: (i.item, i.status))

    note = "\n".join(f"* {i.item}" for i in changeset)

    if note and header:
        note = f"{header}\n{note}"

    return note
