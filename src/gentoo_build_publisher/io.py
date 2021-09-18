"""I/O utils for Gentoo Build Publisher"""
from collections.abc import Iterator
from typing import Protocol


class Readable(Protocol):  # pylint: disable=too-few-public-methods
    """File-like object that can read in chunks"""

    def read(self, size: int) -> bytes:
        """Read at most size bytes from the file"""


class Writable(Protocol):  # pylint: disable=too-few-public-methods
    """File-like object that can write bytes"""

    def write(self, data: bytes) -> int:
        """Write bytes and return the number of bytes written"""


def read_chunks(reader: Readable, chunk_size: int) -> Iterator[bytes]:
    """Iterate chunk_size-chunks over the file-like object"""
    while chunk := reader.read(chunk_size):
        yield chunk


def write_chunks(writer: Writable, chunked_iter: Iterator[bytes]) -> int:
    """Given the chunked_iter iterable, write all chunks to writer"""
    bytes_written = 0

    for chunk in chunked_iter:
        bytes_written += writer.write(chunk)

    return bytes_written
