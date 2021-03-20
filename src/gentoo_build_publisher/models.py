"""
Django models for Gentoo Build Publisher
"""
import os
import uuid

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

    repos_dir = f"{settings.WORK_DIR}/repos"
    binpkgs_dir = f"{settings.WORK_DIR}/binpkgs"

    def __repr__(self) -> str:
        build_name = self.build_name
        build_number = self.build_number
        name = type(self).__name__

        return f"{name}(build_name={build_name!r}, build_number={build_number})"

    def __str__(self) -> str:
        return f"Build #{self.build_number} for {self.build_name}"

    @property
    def url(self) -> str:
        """Return the artifact url for this build"""
        return (
            f"{settings.JENKINS_BASE_URL}/job/{self.build_name}/{self.build_number}"
            f"/artifact/{settings.JENKINS_ARTIFACT_NAME}"
        )

    def publish(self) -> uuid.UUID:
        """Queue the publish task and return the task id"""
        if not os.path.exists(self.artifact_path):
            self.download_artifact()

        tmpdir = f"{settings.WORK_DIR}/tmp/{self.build_name}.{self.build_number}"
        io.extract_tarfile(self.artifact_path, tmpdir)
        io.replace(f"{self.binpkgs_dir}/{self.build_name}", f"{tmpdir}/binpkgs")
        io.replace(f"{self.repos_dir}/{self.build_name}", f"{tmpdir}/repos")
        os.rmdir(tmpdir)

    def download_artifact(self):
        """Download the artifact from Jenkins to self.artifact_path"""
        auth = (settings.JENKINS_USER, settings.JENKINS_API_KEY)
        response = requests.get(self.url, auth=auth, stream=True)
        response.raise_for_status()

        os.makedirs(os.path.dirname(self.artifact_path))

        with open(self.artifact_path, "wb") as artifact_file:
            for chunk in response.iter_content(chunk_size=2048, decode_unicode=False):
                artifact_file.write(chunk)

    @property
    def artifact_path(self):
        """Return artifact path for this build"""

        return (
            f"{settings.WORK_DIR}/artifacts/{self.build_name}/{self.build_number}"
            f"/{settings.JENKINS_ARTIFACT_NAME}"
        )
