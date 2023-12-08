"""Common functions for async jobs

These are basically functions that are wrapped by JobsInterface implementations.  The
core logic is here and the JobsInterface implementations provide the backend-specific
bits like submitting to the task queue, retries, etc.
"""
import logging

import requests.exceptions

from gentoo_build_publisher.common import Build
from gentoo_build_publisher.publisher import BuildPublisher
from gentoo_build_publisher.settings import Settings

HTTP_NOT_FOUND = 404
PUBLISH_FATAL_EXCEPTIONS = (requests.exceptions.HTTPError,)
PULL_RETRYABLE_EXCEPTIONS = (
    EOFError,
    requests.exceptions.ConnectionError,
    requests.exceptions.HTTPError,
)

logger = logging.getLogger(__name__)


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
