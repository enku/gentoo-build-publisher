"""Storage (filesystem) interface for Gentoo Build Publisher"""
from __future__ import annotations

import logging
import os
import shutil
import tarfile
from pathlib import PosixPath
from typing import Iterator, Optional

from gentoo_build_publisher import JENKINS_DEFAULT_CHUNK_SIZE
from gentoo_build_publisher.build import Build, Content, GBPMetadata, Package
from gentoo_build_publisher.settings import Settings

logger = logging.getLogger(__name__)


class StorageBuild:
    """A Build stored on the filesystem"""

    def __init__(self, build: Build, path: PosixPath):
        self.build = build
        self.path = path
        (self.path / "tmp").mkdir(parents=True, exist_ok=True)

    def __repr__(self):
        cls = type(self)
        module = cls.__module__

        return f"{module}.{cls.__name__}({repr(self.path)})"

    @classmethod
    def from_settings(cls, build: Build, my_settings: Settings) -> StorageBuild:
        """Instatiate from settings"""
        return cls(build, my_settings.STORAGE_PATH)

    def get_path(self, item: Content) -> PosixPath:
        """Return the Path of the content type for build

        Were it to be downloaded.
        """
        return self.path / item.value / str(self.build)

    def extract_artifact(
        self,
        byte_stream: Iterator[bytes],
        previous_build: Optional[StorageBuild] = None,
    ):
        """Pull and unpack the artifact

        If `previous_build` is given, then if a file exists in that location it will be
        hard linked to the extracted tree instead of being copied from the artifact.
        This is similiar to the "--link-dest" argument in rsync and is used to save disk
        space.
        """
        if self.pulled():
            return

        artifact_path = (
            self.path
            / "tmp"
            / self.build.name
            / str(self.build.number)
            / "build.tar.gz"
        )
        dirpath = artifact_path.parent
        dirpath.mkdir(parents=True, exist_ok=True)

        with artifact_path.open("wb") as artifact_file:
            for chunk in byte_stream:
                artifact_file.write(chunk)

        logger.info("Extracting build: %s", self.build)
        with tarfile.open(
            artifact_path, mode="r", bufsize=JENKINS_DEFAULT_CHUNK_SIZE
        ) as tar_file:
            tar_file.extractall(dirpath)

        for item in Content:
            src = dirpath / item.value
            dst = self.get_path(item)

            if previous_build:
                shutil.copytree(
                    src,
                    dst,
                    symlinks=True,
                    copy_function=copy_or_link(previous_build.get_path(item), dst),
                )
            else:
                os.renames(src, dst)

        shutil.rmtree(dirpath)
        logger.info("Extracted build: %s", self.build)

    def pulled(self) -> bool:
        """Returns True if build has been pulled

        By "pulled" we mean all Build components exist on the filesystem
        """
        return all(self.get_path(item).exists() for item in Content)

    def publish(self):
        """Make this build 'active'"""
        if not self.pulled():
            raise FileNotFoundError("The build has not been pulled")

        for item in Content:
            path = self.path / item.value / self.build.name
            self.symlink(str(self.build), str(path))

    def published(self) -> bool:
        """Return True if the build currently published.

        By "published" we mean all content are symlinked. Partially symlinked is
        unstable and therefore considered not published.
        """
        return all(
            (symlink := self.path / item.value / self.build.name).exists()
            and os.path.realpath(symlink) == str(self.get_path(item))
            for item in Content
        )

    def delete(self):
        """Delete files/dirs associated with build

        Does not fix dangling symlinks.
        """
        for item in Content:
            shutil.rmtree(self.get_path(item), ignore_errors=True)

    @staticmethod
    def symlink(source: str, target: str):
        """If target is a symlink remove it. If it otherwise exists raise an error"""
        if os.path.islink(target):
            os.unlink(target)
        elif os.path.exists(target):
            raise EnvironmentError(f"{target} exists but is not a symlink")

        os.symlink(source, target)

    def package_index_file(self):
        """Return a file object for the Packages index file"""
        package_index_path = self.get_path(Content.BINPKGS) / "Packages"

        if not package_index_path.exists():
            logger.warning("Build %s is missing package index", self.build)
            raise LookupError(f"{package_index_path} is missing")

        return package_index_path.open(encoding="utf-8")

    def get_packages(self) -> list[Package]:
        """Return the list of packages for this build"""
        packages = []

        with self.package_index_file() as package_index_file:
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

    def get_metadata(self) -> GBPMetadata:
        """Read binpkg/gbp.json and return GBPMetadata instance

        If the file does not exist (e.g. not pulled), raise LookupError
        """
        path = self.get_path(Content.BINPKGS) / "gbp.json"

        if not path.exists():
            raise LookupError("gbp.json does not exist")

        with path.open("r") as gbp_json:
            return GBPMetadata.from_json(gbp_json.read())  # type: ignore # pylint: disable=no-member

    def set_metadata(self, metadata: GBPMetadata):
        """Save metadata to "gbp.json" in the binpkgs directory"""
        path = self.get_path(Content.BINPKGS) / "gbp.json"
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


def copy_or_link(link_dest: PosixPath, dst_root: PosixPath):
    """Create a copytree copy_function that uses rsync's link_dest logic"""

    def copy(src: str, dst: str, follow_symlinks=True):
        relative = PosixPath(dst).relative_to(dst_root)
        target = str(link_dest / relative)
        if quick_check(src, target):
            os.link(target, dst, follow_symlinks=follow_symlinks)
        else:
            shutil.copy2(src, dst, follow_symlinks=follow_symlinks)

    return copy
