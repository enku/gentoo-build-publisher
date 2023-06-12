"""Misc string operations"""
from typing import IO, Iterator


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
    # Skip to the first non-blank line
    try:
        while not (line := next(fobject).rstrip()):
            pass
    except StopIteration:  # EOF
        return

    yield line

    while line := fobject.readline().rstrip():
        yield line


def get_sections(fobject: IO[str]) -> Iterator[list[str]]:
    """Yield the set sections of fobject with non-blank lines"""
    while section := [*until_blank(fobject)]:
        yield section


def get_bool(value: str | bool) -> bool:
    """Return the boolean value of the truthy/falsey string"""
    if isinstance(value, bool):
        return value

    if isinstance(value, bytes):
        value = value.decode("UTF-8")

    if value.lower() in [
        "0",
        "f",
        "false",
        "n",
        "no",
        "off",
    ]:
        return False

    if value.lower() in [
        "1",
        "on",
        "t",
        "true",
        "y",
        "yes",
    ]:
        return True

    raise ValueError(value)
