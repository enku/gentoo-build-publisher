"""GBP types"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

import requests

from gentoo_build_publisher import io
from gentoo_build_publisher.conf import GBPSettings, settings


@dataclass
class Build:
    """A (storage-less) representation of a build (dataclass)"""

    name: str
    number: int

    def __str__(self):
        return f"{self.name}.{self.number}"


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
    def from_settings(cls, my_settings: GBPSettings) -> Storage:
        """Instatiate from settings"""
        return cls(my_settings.HOME_DIR)

    @staticmethod
    def artifact_url(build: Build) -> str:
        """Return the url of the build's artifact on Jenkins"""
        return (
            f"{settings.JENKINS_BASE_URL}/job/{build.name}/{build.number}"
            f"/artifact/{settings.JENKINS_ARTIFACT_NAME}"
        )

    def build_repos(self, build: Build) -> str:
        """Return the path to the build's repos directory"""
        return f"{self.dirname}/repos/{build.name}.{build.number}"

    def build_binpkgs(self, build: Build) -> str:
        """Return the path to the build's binpkgs directory"""
        return f"{self.dirname}/binpkgs/{build.name}.{build.number}"

    def download_artifact(self, build: Build):
        """Download the artifact from Jenkins

        * extract repos to build.repos_dir
        * extract binpkgs to build.binpkgs_dir
        """
        url = self.artifact_url(build)
        auth = (settings.JENKINS_USER, settings.JENKINS_API_KEY)
        response = requests.get(url, auth=auth, stream=True)
        response.raise_for_status()

        path = f"{self.dirname}/tmp/{build.name}{build.number}/build.tar.gz"
        dirpath = os.path.dirname(path)
        os.makedirs(dirpath, exist_ok=True)

        with open(path, "wb") as artifact_file:
            for chunk in response.iter_content(chunk_size=2048, decode_unicode=False):
                artifact_file.write(chunk)

        io.extract_tarfile(path, dirpath)

        os.renames(f"{dirpath}/repos", self.build_repos(build))
        os.renames(f"{dirpath}/binpkgs", self.build_binpkgs(build))

        shutil.rmtree(dirpath)

    def publish(self, build: Build):
        """Make this build 'active'"""
        binpkgs_dir = self.build_binpkgs(build)
        repos_dir = self.build_repos(build)

        if not os.path.exists(repos_dir) and not os.path.exists(binpkgs_dir):
            self.download_artifact(build)

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
