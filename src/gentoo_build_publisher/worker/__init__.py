"""Async Workers for Gentoo Build Publisher"""
import importlib.metadata
import logging
from functools import cache
from typing import Any, Protocol

import requests.exceptions

from gentoo_build_publisher.common import Build
from gentoo_build_publisher.publisher import BuildPublisher
from gentoo_build_publisher.settings import Settings

__all__ = (
    "PULL_RETRYABLE_EXCEPTIONS",
    "Worker",
    "WorkerError",
    "WorkerNotFoundError",
    "delete_build",
    "publish_build",
    "pull_build",
    "purge_machine",
)

HTTP_NOT_FOUND = 404
PUBLISH_FATAL_EXCEPTIONS = (requests.exceptions.HTTPError,)
PULL_RETRYABLE_EXCEPTIONS = (
    EOFError,
    requests.exceptions.ConnectionError,
    requests.exceptions.HTTPError,
)

logger = logging.getLogger(__name__)


class WorkerError(Exception):
    """Errors for workers"""


class WorkerNotFoundError(LookupError, WorkerError):
    """Couldn't find you a worker"""


class WorkerInterface(Protocol):
    """Task Queue Interface"""

    def __init__(self, settings: Settings) -> None:
        """Initialize with the given settings"""

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

    @classmethod
    def work(cls, settings: Settings) -> Any:
        """Run the task worker for this interface"""


@cache
def Worker(settings: Settings) -> WorkerInterface:  # pylint: disable=invalid-name
    """Return the appropriate WorkerInterface based on the given Settings

    Looks at Settings.WORKER_BACKEND and return a WorkerInterface based on that setting.

    Raise WorkerNotFoundError if the setting is invalid.
    """
    try:
        [backend] = importlib.metadata.entry_points(
            group="gentoo_build_publisher.worker_interface",
            name=settings.WORKER_BACKEND,
        )
    except ValueError:
        raise WorkerNotFoundError(settings.WORKER_BACKEND) from None

    worker_class: type[WorkerInterface] = backend.load()

    return worker_class(settings)


#
# Common functions for async workers
#
# These are basically functions that are wrapped by WorkerInterface implementations.
# The core logic is here and the WorkerInterface implementations provide the
# backend-specific bits like submitting to the task queue, retries, etc.
#
def publish_build(build_id: str) -> bool:
    """Publish the build"""
    publisher = BuildPublisher.get_publisher()

    try:
        pull_build(build_id)
    except PUBLISH_FATAL_EXCEPTIONS:
        logger.error("Build %s failed to pull. Not publishing", f"{build_id}")
        return False

    publisher.publish(Build.from_id(build_id))

    return True


def pull_build(build_id: str, *, note: str | None = None) -> None:
    """Pull the build into storage

    If `note` is given, then the build record will be saved with the given note.
    """
    publisher = BuildPublisher.get_publisher()
    build = Build.from_id(build_id)

    try:
        publisher.pull(build, note=note)
    except Exception as error:
        logger.exception("Failed to pull build %s", build)

        # If this is an error due to 404 response don't retry
        if isinstance(error, requests.exceptions.HTTPError):
            response = getattr(error, "response", None)
            if response is not None and response.status_code == HTTP_NOT_FOUND:
                publisher.delete(build)
                raise

        publisher.delete(build)
        raise

    if Settings.from_environ().ENABLE_PURGE:
        purge_machine(build.machine)


def purge_machine(machine: str) -> None:
    """Purge old builds for machine"""
    publisher = BuildPublisher.get_publisher()

    publisher.purge(machine)


def delete_build(build_id: str) -> None:
    """Delete the given build from the db"""
    publisher = BuildPublisher.get_publisher()
    build = Build.from_id(build_id)

    logger.info("Deleting build: %s", build)

    publisher.delete(build)
    logger.info("Deleted build: %s", build)
