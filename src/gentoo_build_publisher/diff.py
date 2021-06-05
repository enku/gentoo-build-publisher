"""Library to show differences between directories

This is made to calculate differences between binpkg directories but can be used for any
similar purpose.
"""
import filecmp
import os
from typing import Generator, Literal, Tuple

FileComp = Tuple[Literal[-1, 0, 1], str]

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


def generate(
    left: str, right: str, dircmp: filecmp.dircmp
) -> Generator[FileComp, None, None]:
    """Recursive generator for file comparisions"""
    for subcmp in dircmp.subdirs.values():

        for item in subcmp.left_only:
            path = f"{subcmp.left}/{item}"

            if os.path.isdir(path):
                continue

            yield (-1, path_to_pkg(left, path))

        for item in subcmp.right_only:
            path = f"{subcmp.right}/{item}"

            if os.path.isdir(path):
                continue

            yield (1, path_to_pkg(right, path))

        for item in subcmp.diff_files:
            path1 = f"{subcmp.left}/{item}"
            path2 = f"{subcmp.right}/{item}"

            if os.path.isdir(path1) and os.path.isdir(path2):
                continue

            yield (0, path_to_pkg(left, path1))
            yield (0, path_to_pkg(right, path2))

        yield from generate(left, right, subcmp)


def dirdiff(left: str, right: str) -> Generator[FileComp, None, None]:
    """Generate differences between to directory paths"""
    dircmp = filecmp.dircmp(left, right)

    yield from generate(left, right, dircmp)
