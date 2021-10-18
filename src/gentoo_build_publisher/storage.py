"""Storage (filesystem) interface for Gentoo Build Publisher"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tarfile
from pathlib import PosixPath
from typing import Iterator, Optional

from gentoo_build_publisher import JENKINS_DEFAULT_CHUNK_SIZE
from gentoo_build_publisher.build import Build, Content, Package
from gentoo_build_publisher.settings import Settings

logger = logging.getLogger(__name__)

RSYNC_FLAGS = ["--archive", "--inplace", "--no-inc-recursive", "--quiet"]


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

        If `previous_build` is given, then the rsync program will be used and it's
        `--link-dest` option will used to hard link with the previous build's content,
        preserving space.  See the `rsync(1)` documentation for details.
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
                previous_path = previous_build.get_path(item)

                if previous_path.exists():
                    command = [
                        "rsync",
                        *RSYNC_FLAGS,
                        f"--link-dest={previous_path}",
                        "--",
                        f"{src}/",
                        f"{dst}/",
                    ]
                    subprocess.run(command, check=True)
                    continue

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
                    )
                )

        return packages
