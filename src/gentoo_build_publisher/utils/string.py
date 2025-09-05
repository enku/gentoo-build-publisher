"""Misc string operations"""

import re
from functools import lru_cache
from typing import IO, Iterator, cast

CPV_RE = re.compile(r"(.*)/(.*)-([0-9].*)")


def namevalue(string: str, delim: str) -> tuple[str, str]:
    """Split string into a name/value pair

    Raise ValueError if delim does not exist in the string.
    """
    name, delim, value = string.partition(delim)

    if not delim:
        raise ValueError(f"String did not contain delimiter: {delim!r}")

    return name.strip(), value.lstrip()


def until_blank(fobject: IO[str]) -> Iterator[str]:
    """Yield lines from fobject until a blank line is encountered

    Skip initial blank lines in the file.
    Do not return the blank line(s).
    """
    stripped_lines = (line.strip() for line in fobject)

    # Skip to the first non-blank line
    for line in stripped_lines:
        if line:
            break
    else:
        return

    yield line

    for line in stripped_lines:
        if not line:
            return
        yield line


def get_sections(fobject: IO[str]) -> Iterator[list[str]]:
    """Yield the set sections of fobject with non-blank lines"""
    while section := list(until_blank(fobject)):
        yield section


@lru_cache(256)
def split_pkg(cpv: str) -> tuple[str, str, str]:
    """Split the given cpv into it's three parts"""
    if pattern := CPV_RE.search(cpv):
        return cast(tuple[str, str, str], tuple(pattern.groups()))

    raise ValueError(f"Bad regex/cpv: {CPV_RE.pattern!r}/{cpv!r}")
