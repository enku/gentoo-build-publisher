"""I/O utils for Gentoo Build Publisher"""
from __future__ import annotations

from collections.abc import Iterator
from typing import IO


def read_chunks(reader: IO[bytes], chunk_size: int) -> Iterator[bytes]:
    """Iterate chunk_size-chunks over the file-like object"""
    while chunk := reader.read(chunk_size):
        yield chunk


def write_chunks(writer: IO[bytes], chunked_iter: Iterator[bytes]) -> int:
    """Given the chunked_iter iterable, write all chunks to writer"""
    bytes_written = 0

    for chunk in chunked_iter:
        bytes_written += writer.write(chunk)

    return bytes_written
