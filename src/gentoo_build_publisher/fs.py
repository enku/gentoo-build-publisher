"""Filesystem Operations"""

import logging
import os
import shutil
import tarfile
from pathlib import Path
from typing import IO, Callable, Iterable, TypeVar

_T = TypeVar("_T", bytes, str)

logger = logging.getLogger(__name__)


def init_root(root: Path, subdirs: list[str] | None) -> None:
    """Initialize storage root, if necessary"""
    root.mkdir(parents=True, exist_ok=True)

    for subdir in subdirs or []:
        root.joinpath(subdir).mkdir(exist_ok=True)


def extract(infile: Path, outdir: Path) -> None:
    """Extract the given (compressed) tarfile into the given directory

    The directory is created if it does not exist.
    """
    logger.info("Extracting %s to %s", infile, outdir)

    with tarfile.open(infile, mode="r") as tar_file:
        tar_file.extractall(outdir)

    logger.info("Extracted %s to %s", infile, outdir)


def save_stream(stream: Iterable[_T], outfile: IO[_T]) -> None:
    """Given the byte stream, save and buffer it to given outfile

    These are buffered writes if the given file is opened with buffering.
    """
    outfile.writelines(stream)
    outfile.flush()


def copy_path(src: Path, dst: Path, link_dest: Path | None) -> None:
    """Copy the given src path into the given dst path

    If link_dest is given, use its files and, when possible, create hard links
    from link_dest build's files to build's when they are the same file.

    If dst already exists, remove it before copying.
    """
    if dst.exists():
        logger.warning("Extract destination already exists: %s. Removing", dst)
        shutil.rmtree(dst)

    if link_dest is not None:
        copy = copy_or_link(link_dest, dst)
        shutil.copytree(src, dst, symlinks=True, copy_function=copy)
    else:
        os.renames(src, dst)


def quick_check(file1: str, file2: str) -> bool:
    """Do an rsync-style quick check. Return true if files appear identical"""
    try:
        stat1 = os.stat(file1, follow_symlinks=False)
        stat2 = os.stat(file2, follow_symlinks=False)
    except FileNotFoundError:
        return False

    return stat1.st_mtime == stat2.st_mtime and stat1.st_size == stat2.st_size


def copy_or_link(link_dest: Path, dst_root: Path) -> Callable[[str, str], None]:
    """Create a shutil.copytree copy_function that uses rsync's link_dest logic

    Utilize shutil.copy2 (the default copy_function) when the quick_check() fails,
    otherwise instead of copying create a (hard) link from source to destination.

    https://docs.python.org/3/library/shutil.html#shutil.copytree
    """

    def copy(src: str, dst: str, follow_symlinks: bool = True) -> None:
        relative = Path(dst).relative_to(dst_root)
        target = str(link_dest / relative)
        if quick_check(src, target):
            os.link(target, dst, follow_symlinks=follow_symlinks)
        else:
            shutil.copy2(src, dst, follow_symlinks=follow_symlinks)

    return copy


def symlink(source: str, target: str) -> None:
    """If target is a symlink remove it. If it otherwise exists raise an error"""
    if os.path.islink(target):
        os.unlink(target)
    elif os.path.exists(target):
        raise EnvironmentError(f"{target} exists but is not a symlink")

    os.symlink(source, target)


def check_symlink(symlink_: str, target: str) -> bool:
    """Return True if the given symlinks point to the given target"""
    if not os.path.islink(symlink_):
        return False

    return os.path.realpath(symlink_) == target
