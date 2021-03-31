"""GBP types"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any, Dict, Generator

import requests

from gentoo_build_publisher import io


class Settings:
    """GBP Settings"""

    DEFAULTS = {
        "JENKINS_ARTIFACT_NAME": "build.tar.gz",
        "JENKINS_API_KEY": "JENKINS_API_KEY_REQUIRED",
        "JENKINS_BASE_URL": "http://jenkins/Gentoo",
        "JENKINS_USER": "jenkins",
        "HOME_DIR": "/var/lib/gentoo-build-publisher",
    }

    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            if name not in self.DEFAULTS:
                raise ValueError(name)
            value = self.validate_setting(name, value)
            setattr(self, name, value)

    def __getattr__(self, name):
        if name not in self.DEFAULTS:
            raise AttributeError(name)

        value = self.DEFAULTS[name]
        value = self.validate_setting(name, value)

        setattr(self, name, value)

        return value

    def validate_setting(self, _attr, value):  # pylint: disable=no-self-use
        """Validate a settings"""
        # For now we don't do any special validation
        return str(value)

    @classmethod
    def from_dict(cls, prefix, data_dict: Dict[str, Any]) -> Settings:
        """Return Settings instantiated from a dict"""
        prefix_len = len(prefix)
        kwargs = {}

        for name, value in data_dict.items():
            if not name.startswith(prefix):
                continue

            name = name[prefix_len:]

            if name not in cls.DEFAULTS:
                continue

            kwargs[name] = value

        return cls(**kwargs)

    @classmethod
    def from_environ(cls, prefix: str = "BUILD_PUBLISHER_") -> Settings:
        """Return settings instantiated from environment variables"""
        return cls.from_dict(prefix, os.environ)


@dataclass
class Build:
    """A Representation of a Jenkins build"""

    name: str
    number: int

    def __str__(self):
        return f"{self.name}.{self.number}"


@dataclass
class Jenkins:
    """Interface to Jenkins"""

    base_url: str
    user: str
    api_key: str
    artifact_name: str = "build.tar.gz"

    def build_url(self, build: Build) -> str:
        """Return the artifact url for build"""
        return (
            f"{self.base_url}/job/{build.name}/{build.number}"
            f"/artifact/{self.artifact_name}"
        )

    def download_artifact(self, build: Build) -> Generator[bytes, None, None]:
        """Download and yield the build artifact in chunks of bytes"""
        auth = (self.user, self.api_key)
        url = self.build_url(build)
        response = requests.get(url, auth=auth, stream=True)
        response.raise_for_status()

        return response.iter_content(chunk_size=2048, decode_unicode=False)

    @classmethod
    def from_settings(cls, settings: Settings):
        """Return a Jenkins instance given settings"""
        return cls(
            base_url=settings.JENKINS_BASE_URL,
            artifact_name=settings.JENKINS_ARTIFACT_NAME,
            user=settings.JENKINS_USER,
            api_key=settings.JENKINS_API_KEY,
        )


class Storage:
    """Storage (HOME_DIR) for gentoo_build_publisher"""

    def __init__(self, dirname: str):
        self.dirname = dirname
        self.binpkgs = f"{self.dirname}/binpkgs"
        self.repos = f"{self.dirname}/repos"

        os.makedirs(f"{self.dirname}/tmp", exist_ok=True)
        os.makedirs(self.binpkgs, exist_ok=True)
        os.makedirs(self.repos, exist_ok=True)

    @classmethod
    def from_settings(cls, my_settings: Settings) -> Storage:
        """Instatiate from settings"""
        return cls(my_settings.HOME_DIR)

    def build_repos(self, build: Build) -> str:
        """Return the path to the build's repos directory"""
        return f"{self.dirname}/repos/{build.name}.{build.number}"

    def build_binpkgs(self, build: Build) -> str:
        """Return the path to the build's binpkgs directory"""
        return f"{self.dirname}/binpkgs/{build.name}.{build.number}"

    def download_artifact(self, build: Build, jenkins: Jenkins):
        """Download the artifact from Jenkins

        * extract repos to build.repos_dir
        * extract binpkgs to build.binpkgs_dir
        """
        path = f"{self.dirname}/tmp/{build.name}{build.number}/build.tar.gz"
        dirpath = os.path.dirname(path)
        os.makedirs(dirpath, exist_ok=True)

        with open(path, "wb") as artifact_file:
            for chunk in jenkins.download_artifact(build):
                artifact_file.write(chunk)

        io.extract_tarfile(path, dirpath)

        os.renames(f"{dirpath}/repos", self.build_repos(build))
        os.renames(f"{dirpath}/binpkgs", self.build_binpkgs(build))

        shutil.rmtree(dirpath)

    def publish(self, build: Build, jenkins: Jenkins):
        """Make this build 'active'"""
        binpkgs_dir = self.build_binpkgs(build)
        repos_dir = self.build_repos(build)

        if not os.path.exists(repos_dir) and not os.path.exists(binpkgs_dir):
            self.download_artifact(build, jenkins)

        io.symlink(str(build), f"{self.dirname}/repos/{build.name}")
        io.symlink(str(build), f"{self.dirname}/binpkgs/{build.name}")

    def published(self, build: Build) -> bool:
        """Return True if the build currently published.

        By "published" we mean both repos and binpkgs symlinks point to the build
        """
        repo_symlink = f"{self.repos}/{build.name}"
        binpkg_symlink = f"{self.binpkgs}/{build.name}"

        if not os.path.exists(repo_symlink) or not os.path.exists(binpkg_symlink):
            return False

        if os.path.realpath(repo_symlink) != self.build_repos(build):
            return False

        if os.path.realpath(binpkg_symlink) != self.build_binpkgs(build):
            return False

        return True

    def delete_build(self, build: Build):
        """Delete files/dirs associated with build

        Does not fix dangling symlinks.
        """
        binpkgs_dir = self.build_binpkgs(build)
        repos_dir = self.build_repos(build)

        shutil.rmtree(binpkgs_dir, ignore_errors=True)
        shutil.rmtree(repos_dir, ignore_errors=True)
