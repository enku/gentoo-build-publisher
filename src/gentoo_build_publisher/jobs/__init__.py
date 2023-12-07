"""Async Jobs for Gentoo Build Publisher"""
from typing import Protocol

from gentoo_build_publisher.jobs.celery import CeleryJobs


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
