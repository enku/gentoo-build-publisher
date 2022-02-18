"""Storage (filesystem) interface for Gentoo Build Publisher"""
from __future__ import annotations

import logging
import os
import shutil
import tarfile
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import IO, Iterator

from gentoo_build_publisher import JENKINS_DEFAULT_CHUNK_SIZE
from gentoo_build_publisher.build import BuildID, Content, GBPMetadata, Package
from gentoo_build_publisher.settings import Settings

logger = logging.getLogger(__name__)


class Storage:
    """Filesystem storage for Gentoo Build Publisher"""

    def __init__(self, path: Path):
        self.path = path
        self.tmpdir = self.path / "tmp"
        self.tmpdir.mkdir(parents=True, exist_ok=True)

    def __repr__(self):
        cls = type(self)
        module = cls.__module__

        return f"{module}.{cls.__name__}({repr(self.path)})"

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return self.path == other.path

    @classmethod
    def from_settings(cls, settings: Settings) -> Storage:
        """Instatiate from settings"""
        return cls(settings.STORAGE_PATH)

    @lru_cache(maxsize=256 * len(Content))
    def get_path(self, build_id: BuildID, item: Content) -> Path:
        """Return the Path of the content type for build

        Were it to be downloaded.
        """
        return self.path / item.value / build_id

    def extract_artifact(
        self,
        build_id: BuildID,
        byte_stream: Iterator[bytes],
        previous_build: BuildID | None = None,
    ):
        """Pull and unpack the artifact

        If `previous_build` is given, then if a file exists in that location it will be
        hard linked to the extracted tree instead of being copied from the artifact.
        This is similiar to the "--link-dest" argument in rsync and is used to save disk
        space.
        """
        if self.pulled(build_id):
            return

        with tempfile.NamedTemporaryFile(dir=self.tmpdir, suffix="tar.gz") as artifact:
            for chunk in byte_stream:
                artifact.write(chunk)

            artifact.flush()

            logger.info("Extracting build: %s", build_id)
            bufsize = JENKINS_DEFAULT_CHUNK_SIZE

            with tarfile.open(artifact.name, mode="r", bufsize=bufsize) as tar_file:
                self._extract(build_id, tar_file, previous_build)

            logger.info("Extracted build: %s", build_id)

    def _extract(
        self, build_id, tar_file: tarfile.TarFile, previous_build: BuildID | None
    ):
        with tempfile.TemporaryDirectory(dir=self.tmpdir) as dirpath:
            tar_file.extractall(dirpath)

            for item in Content:
                src = Path(dirpath) / item.value
                dst = self.get_path(build_id, item)

                if dst.exists():
                    msg = "Extract destination already exists: %s. Removing"
                    logger.warning(msg, dst)
                    shutil.rmtree(dst)

                if previous_build:
                    copy = copy_or_link(self.get_path(previous_build, item), dst)
                    shutil.copytree(src, dst, symlinks=True, copy_function=copy)
                else:
                    os.renames(src, dst)

    def pulled(self, build_id: BuildID) -> bool:
        """Returns True if build has been pulled

        By "pulled" we mean all Build components exist on the filesystem
        """
        return all(self.get_path(build_id, item).exists() for item in Content)

    def publish(self, build_id: BuildID):
        """Make this build 'active'"""
        if not self.pulled(build_id):
            raise FileNotFoundError("The build has not been pulled")

        for item in Content:
            path = self.path / item.value / build_id.name
            self.symlink(build_id, str(path))

    def published(self, build_id: BuildID) -> bool:
        """Return True if the build currently published.

        By "published" we mean all content are symlinked. Partially symlinked is
        unstable and therefore considered not published.
        """
        return all(
            (symlink := self.path / item.value / build_id.name).exists()
            and os.path.realpath(symlink) == str(self.get_path(build_id, item))
            for item in Content
        )

    def delete(self, build_id: BuildID) -> None:
        """Delete files/dirs associated with build

        Does not fix dangling symlinks.
        """
        for item in Content:
            shutil.rmtree(self.get_path(build_id, item), ignore_errors=True)

    @staticmethod
    def symlink(source: str, target: str) -> None:
        """If target is a symlink remove it. If it otherwise exists raise an error"""
        if os.path.islink(target):
            os.unlink(target)
        elif os.path.exists(target):
            raise EnvironmentError(f"{target} exists but is not a symlink")

        os.symlink(source, target)

    def package_index_file(self, build_id: BuildID) -> IO[str]:
        """Return a file object for the Packages index file"""
        package_index_path = self.get_path(build_id, Content.BINPKGS) / "Packages"

        if not package_index_path.exists():
            logger.warning("Build %s is missing package index", build_id)
            raise LookupError(f"{package_index_path} is missing")

        return package_index_path.open(encoding="utf-8")

    def get_packages(self, build_id: BuildID) -> list[Package]:
        """Return the list of packages for this build"""
        packages = []

        with self.package_index_file(build_id) as package_index_file:
            # Skip preamble (for now)
            while package_index_file.readline().rstrip():
                pass

            while True:
                lines = []
                while line := package_index_file.readline().rstrip():
                    lines.append(line)
                if not lines:
                    break

                package_info = {}
                for line in lines:
                    key, _, value = line.partition(":")
                    key = key.rstrip().lower()
                    value = value.lstrip()
                    package_info[key] = value

                packages.append(
                    Package(
                        package_info["cpv"],
                        package_info["repo"],
                        package_info["path"],
                        int(package_info["build_id"]),
                        int(package_info["size"]),
                        int(package_info["build_time"]),
                    )
                )

        return packages

    def get_metadata(self, build_id: BuildID) -> GBPMetadata:
        """Read binpkg/gbp.json and return GBPMetadata instance

        If the file does not exist (e.g. not pulled), raise LookupError
        """
        path = self.get_path(build_id, Content.BINPKGS) / "gbp.json"

        if not path.exists():
            raise LookupError("gbp.json does not exist")

        with path.open("r") as gbp_json:
            return GBPMetadata.from_json(gbp_json.read())  # type: ignore # pylint: disable=no-member

    def set_metadata(self, build_id: BuildID, metadata: GBPMetadata) -> None:
        """Save metadata to "gbp.json" in the binpkgs directory"""
        path = self.get_path(build_id, Content.BINPKGS) / "gbp.json"
        with path.open("w") as gbp_json:
            gbp_json.write(metadata.to_json())  # type: ignore # pylint: disable=no-member


def quick_check(file1: str, file2: str) -> bool:
    """Do an rsync-style quick check. Return true if files appear identical"""
    try:
        stat1 = os.stat(file1, follow_symlinks=False)
        stat2 = os.stat(file2, follow_symlinks=False)
    except FileNotFoundError:
        return False

    return stat1.st_mtime == stat2.st_mtime and stat1.st_size == stat2.st_size


def copy_or_link(link_dest: Path, dst_root: Path):
    """Create a copytree copy_function that uses rsync's link_dest logic"""

    def copy(src: str, dst: str, follow_symlinks=True):
        relative = Path(dst).relative_to(dst_root)
        target = str(link_dest / relative)
        if quick_check(src, target):
            os.link(target, dst, follow_symlinks=follow_symlinks)
        else:
            shutil.copy2(src, dst, follow_symlinks=follow_symlinks)

    return copy
