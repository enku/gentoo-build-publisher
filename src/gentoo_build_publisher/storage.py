"""Storage (filesystem) interface for Gentoo Build Publisher"""
from __future__ import annotations

import os
import shutil
import tarfile
from pathlib import PosixPath
from typing import Iterator

from gentoo_build_publisher.build import Build, Content
from gentoo_build_publisher.settings import Settings


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

    def extract_artifact(self, byte_stream: Iterator[bytes]):
        """Pull and unpack the artifact"""
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

        with tarfile.open(artifact_path, mode="r") as tar_file:
            tar_file.extractall(dirpath)

        for item in Content:
            src = dirpath / item.value
            dst = self.get_path(item)
            os.renames(src, dst)

        shutil.rmtree(dirpath)

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
