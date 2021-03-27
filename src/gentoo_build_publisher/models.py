"""
Django models for Gentoo Build Publisher
"""
import os
import shutil
from typing import Any, Dict

import requests
from django.db import models

from gentoo_build_publisher import io
from gentoo_build_publisher.conf import settings


class Build(models.Model):
    """The main table for GBP"""

    # The Jenkins build name
    build_name = models.CharField(max_length=255, db_index=True)

    # The Jenkins build number
    build_number = models.PositiveIntegerField()

    # when this build was submitted to GBP
    submitted = models.DateTimeField()

    # When this build's publish task completed
    completed = models.DateTimeField(null=True)

    # The build's task id
    task_id = models.UUIDField(null=True)

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        constraints = [
            models.UniqueConstraint(
                fields=["build_name", "build_number"], name="unique_build"
            )
        ]

    def __repr__(self) -> str:
        build_name = self.build_name
        build_number = self.build_number
        name = type(self).__name__

        return f"{name}(build_name={build_name!r}, build_number={build_number})"

    def __str__(self) -> str:
        return f"{self.build_name}.{self.build_number}"

    @property
    def url(self) -> str:
        """Return the artifact url for this build"""
        return (
            f"{settings.JENKINS_BASE_URL}/job/{self.build_name}/{self.build_number}"
            f"/artifact/{settings.JENKINS_ARTIFACT_NAME}"
        )

    @property
    def repos_dir(self) -> str:
        """Return the path to the repos directory"""
        return  f"{settings.HOME_DIR}/repos/{self}"

    @property
    def binpkgs_dir(self) -> str:
        """Return the path to the binpkgs directory"""
        return  f"{settings.HOME_DIR}/binpkgs/{self}"

    def publish(self):
        """Make this build 'active'"""
        if not os.path.exists(self.repos_dir) and not os.path.exists(self.binpkgs_dir):
            self.download_artifact()

        io.symlink(str(self), f"{settings.HOME_DIR}/repos/{self.build_name}")
        io.symlink(str(self), f"{settings.HOME_DIR}/binpkgs/{self.build_name}")

    def download_artifact(self):
        """Download the artifact from Jenkins

        * extract repos to self.repos_dir
        * extract binpkgs to self.binpkgs_dir
        """
        auth = (settings.JENKINS_USER, settings.JENKINS_API_KEY)
        response = requests.get(self.url, auth=auth, stream=True)
        response.raise_for_status()

        path = f"{settings.HOME_DIR}/tmp/{self}/build.tar.gz"
        dirpath = os.path.dirname(path)
        os.makedirs(dirpath, exist_ok=True)

        with open(path, "wb") as artifact_file:
            for chunk in response.iter_content(chunk_size=2048, decode_unicode=False):
                artifact_file.write(chunk)

        io.extract_tarfile(path, dirpath)

        os.renames(f"{dirpath}/repos", self.repos_dir)
        os.renames(f"{dirpath}/binpkgs", self.binpkgs_dir)

        shutil.rmtree(dirpath)

    def delete(self, using=None, keep_parents=False):
        # The reason to call super().delete() before removing the directories is if for
        # some reason super().delete() fails we don't want to delete the directories.
        super().delete(using=using, keep_parents=keep_parents)

        shutil.rmtree(self.binpkgs_dir, ignore_errors=True)
        shutil.rmtree(self.repos_dir, ignore_errors=True)

    @property
    def published(self):
        """Return True if this build currently published.

        By "published" we mean both repose and binpkgs symlinks point to this build
        """
        repo_symlink = f"{settings.HOME_DIR}/repos/{self.build_name}"
        binpkg_symlink = f"{settings.HOME_DIR}/binpkgs/{self.build_name}"

        if not os.path.exists(repo_symlink) or not os.path.exists(binpkg_symlink):
            return False

        if os.path.realpath(repo_symlink) != f"{settings.HOME_DIR}/repos/{self}":
            return False

        if os.path.realpath(binpkg_symlink) != f"{settings.HOME_DIR}/binpkgs/{self}":
            return False

        return True

    def as_dict(self) -> Dict[str, Any]:
        """Convert build instance attributes to a dict"""
        return {
            "buildName": self.build_name,
            "buildNumber": self.build_number,
            "published": self.published,
            "url": self.url,
        }
