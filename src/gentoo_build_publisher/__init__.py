"""Gentoo Build Publisher"""
from __future__ import annotations

import os
import shutil
import tarfile
from dataclasses import dataclass
from enum import Enum, unique
from pathlib import PosixPath
from typing import Any, Dict, Generator, Optional

import requests
from pydantic import AnyHttpUrl, BaseModel
from yarl import URL


# NOTE: Using pydantic's BaseSettings was considered here but was considered too much
# "magic" and explicitly calling .from_environ() preferred.
class Settings(BaseModel):
    """GBP Settings"""

    ENABLE_PURGE: bool = False
    JENKINS_ARTIFACT_NAME: str = "build.tar.gz"
    JENKINS_API_KEY: Optional[str] = None
    JENKINS_BASE_URL: AnyHttpUrl
    JENKINS_USER: Optional[str] = None
    STORAGE_PATH: PosixPath

    @classmethod
    def from_dict(cls, prefix: str, data_dict: Dict[str, Any]) -> Settings:
        """Return Settings instantiated from a dict"""
        return cls(
            **{
                key: value
                for key in cls.__fields__
                if (value := data_dict.get(f"{prefix}{key}")) is not None
            }
        )

    @classmethod
    def from_environ(cls, prefix: str = "BUILD_PUBLISHER_") -> Settings:
        """Return settings instantiated from environment variables"""
        return cls.from_dict(prefix, os.environ)


@dataclass
class Build:
    """A Representation of a Jenkins build artifact"""

    name: str
    number: int

    @unique
    class Content(Enum):
        """Each build (should) contain these contents"""

        REPOS = "repos"
        BINPKGS = "binpkgs"
        ETC_PORTAGE = "etc-portage"
        VAR_LIB_PORTAGE = "var-lib-portage"

    def __str__(self):
        return f"{self.name}.{self.number}"


@dataclass
class Jenkins:
    """Interface to Jenkins"""

    base_url: URL
    user: Optional[str] = None
    api_key: Optional[str] = None
    artifact_name: str = "build.tar.gz"

    def build_url(self, build: Build) -> URL:
        """Return the artifact url for build"""
        return (
            self.base_url
            / "job"
            / build.name
            / str(build.number)
            / "artifact"
            / self.artifact_name
        )

    def download_artifact(self, build: Build) -> Generator[bytes, None, None]:
        """Download and yield the build artifact in chunks of bytes"""
        auth = None
        if self.user is not None and self.api_key is not None:
            auth = (self.user, self.api_key)

        url = self.build_url(build)
        response = requests.get(str(url), auth=auth, stream=True)
        response.raise_for_status()

        return response.iter_content(chunk_size=2048, decode_unicode=False)

    @classmethod
    def from_settings(cls, settings: Settings):
        """Return a Jenkins instance given settings"""
        return cls(
            base_url=URL(settings.JENKINS_BASE_URL),
            artifact_name=settings.JENKINS_ARTIFACT_NAME,
            user=settings.JENKINS_USER,
            api_key=settings.JENKINS_API_KEY,
        )


class Storage:
    """Storage for gentoo_build_publisher"""

    def __init__(self, path: PosixPath):
        self.path = path
        (self.path / "tmp").mkdir(parents=True, exist_ok=True)

    def __repr__(self):
        cls = type(self)
        module = cls.__module__

        return f"{module}.{cls.__name__}({repr(self.path)})"

    @classmethod
    def from_settings(cls, my_settings: Settings) -> Storage:
        """Instatiate from settings"""
        return cls(my_settings.STORAGE_PATH)

    def get_path(self, build: Build, item: Build.Content) -> PosixPath:
        """Return the Path of the content type for build

        Were it to be downloaded.
        """
        return self.path / item.value / str(build)

    def download_artifact(self, build: Build, jenkins: Jenkins):
        """Download the artifact from Jenkins

        * extract repos to build.repos_dir
        * extract binpkgs to build.binpkgs_dir
        """
        artifact_path = (
            self.path / "tmp" / build.name / str(build.number) / "build.tar.gz"
        )
        dirpath = artifact_path.parent
        dirpath.mkdir(parents=True, exist_ok=True)

        with artifact_path.open("wb") as artifact_file:
            for chunk in jenkins.download_artifact(build):
                artifact_file.write(chunk)

        with tarfile.open(artifact_path, mode="r") as tar_file:
            tar_file.extractall(dirpath)

        for item in build.Content:
            src = dirpath / item.value
            dst = self.get_path(build, item)
            os.renames(src, dst)

        shutil.rmtree(dirpath)

    def publish(self, build: Build, jenkins: Jenkins):
        """Make this build 'active'"""

        for item in build.Content:
            path = self.get_path(build, item)
            if not path.exists():
                self.download_artifact(build, jenkins)
                break

        for item in build.Content:
            path = self.path / item.value / build.name
            self.symlink(str(build), str(path))

    def published(self, build: Build) -> bool:
        """Return True if the build currently published.

        By "published" we mean all content are symlinked. Partially symlinked is
        unstable and therefore considered not published.
        """
        for item in build.Content:
            symlink = self.path / item.value / build.name

            if not symlink.exists():
                return False

            if os.path.realpath(symlink) != str(self.get_path(build, item)):
                return False

        return True

    def delete_build(self, build: Build):
        """Delete files/dirs associated with build

        Does not fix dangling symlinks.
        """
        for item in build.Content:
            shutil.rmtree(self.get_path(build, item), ignore_errors=True)

    @staticmethod
    def symlink(source: str, target: str):
        """If target is a symlink remove it. If it otherwise exists raise an error"""
        if os.path.islink(target):
            os.unlink(target)
        elif os.path.exists(target):
            raise EnvironmentError(f"{target} exists but is not a symlink")

        os.symlink(source, target)


default_app_config = "gentoo_build_publisher.apps.GentooBuildPublisherConfig"
