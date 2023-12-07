"""Async Jobs for Gentoo Build Publisher"""
from __future__ import annotations

import logging
from typing import Protocol

from gentoo_build_publisher import tasks as celery

HTTP_NOT_FOUND = 404

logger = logging.getLogger(__name__)
jobs: JobsInterface


class JobsInterface(Protocol):
    """Task Queue Interface"""

    def publish_build(self, build_id: str) -> None:
        """Publish the build"""

    def pull_build(self, build_id: str, *, note: str | None = None) -> None:
        """Pull the build into storage

        If `note` is given, then the build record will be saved with the given note.
        """

    def purge_machine(self, machine: str) -> None:
        """Purge old builds for machine"""

    def delete_build(self, build_id: str) -> None:
        """Delete the given build from the db"""


class CeleryJobs:
    """Celery JobsInterface"""

    def publish_build(self, build_id: str) -> None:
        """Publish the build"""
        celery.publish_build.delay(build_id)

    def pull_build(self, build_id: str, *, note: str | None = None) -> None:
        """Pull the build into storage

        If `note` is given, then the build record will be saved with the given note.
        """
        celery.pull_build.delay(build_id, note=note)

    def purge_machine(self, machine: str) -> None:
        """Purge old builds for machine"""
        celery.purge_machine.delay(machine)

    def delete_build(self, build_id: str) -> None:
        """Delete the given build from the db"""
        celery.delete_build.delay(build_id)


def publish_build(build_id: str) -> None:
    """Publish the build"""
    CeleryJobs().publish_build(build_id)


def pull_build(build_id: str, *, note: str | None = None) -> None:
    """Pull the build into storage

    If `note` is given, then the build record will be saved with the given note.
    """
    CeleryJobs().pull_build(build_id, note=note)


def purge_machine(machine: str) -> None:
    """Purge old builds for machine"""
    CeleryJobs().purge_machine(machine)


def delete_build(build_id: str) -> None:
    """Delete the given build from the db"""
    CeleryJobs().delete_build(build_id)
