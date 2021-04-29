"""Gentoo Build Publisher"""
from __future__ import annotations

import os
import shutil
import tarfile
from dataclasses import dataclass
from typing import Any, Dict, Generator

import requests


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

    @staticmethod
    def validate_setting(_attr, value):
        """Validate a settings"""
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
    """A Representation of a Jenkins build artifact"""

    name: str
    number: int

    # Each build (should) contain these contents
    contents = ["repos", "binpkgs", "etc-portage", "var-lib-portage"]

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
        os.makedirs(f"{self.dirname}/tmp", exist_ok=True)

    def __repr__(self):
        cls = type(self)
        module = cls.__module__

        return f"{module}.{cls.__name__}({repr(self.dirname)})"

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

    def build_etc_portage(self, build: Build) -> str:
        """Return the path to the build's /etc/portage directory"""
        return f"{self.dirname}/etc-portage/{build.name}.{build.number}"

    def build_var_lib_portage(self, build: Build) -> str:
        """Return the path to the build's /var_lib/portage directory"""
        return f"{self.dirname}/var-lib-portage/{build.name}.{build.number}"

    def path(self, build: Build, content_type: str) -> str:
        """Return the path of the content_type for build

        Were it to be downloaded.
        """
        assert content_type in build.contents

        return f"{self.dirname}/{content_type}/{build}"

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

        with tarfile.open(path, mode="r") as tar_file:
            tar_file.extractall(dirpath)

        for item in build.contents:
            src = f"{dirpath}/{item}"
            dst = self.path(build, item)
            os.renames(src, dst)

        shutil.rmtree(dirpath)

    def publish(self, build: Build, jenkins: Jenkins):
        """Make this build 'active'"""

        for item in build.contents:
            if not os.path.exists(self.path(build, item)):
                self.download_artifact(build, jenkins)
                break

        for item in build.contents:
            self.symlink(str(build), f"{self.dirname}/{item}/{build.name}")

    def published(self, build: Build) -> bool:
        """Return True if the build currently published.

        By "published" we mean all content are symlinked. Partially symlinked is
        unstable and therefore considered not published.
        """
        for item in build.contents:
            symlink = f"{self.dirname}/{item}/{build.name}"

            if not os.path.exists(symlink):
                return False

            if os.path.realpath(symlink) != self.path(build, item):
                return False

        return True

    def delete_build(self, build: Build):
        """Delete files/dirs associated with build

        Does not fix dangling symlinks.
        """
        for item in build.contents:
            shutil.rmtree(self.path(build, item), ignore_errors=True)

    @staticmethod
    def symlink(source: str, target: str):
        """If target is a symlink remove it. If it otherwise exists raise an error"""
        if os.path.islink(target):
            os.unlink(target)
        elif os.path.exists(target):
            raise EnvironmentError(f"{target} exists but is not a symlink")

        os.symlink(source, target)
