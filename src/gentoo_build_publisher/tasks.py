"""Celery tasks for Gentoo Build Publisher"""
from __future__ import annotations

import logging

import requests
import requests.exceptions
from celery import shared_task

from gentoo_build_publisher.common import Build
from gentoo_build_publisher.publisher import get_publisher
from gentoo_build_publisher.settings import Settings

PUBLISH_FATAL_EXCEPTIONS = (requests.exceptions.HTTPError,)
PULL_RETRYABLE_EXCEPTIONS = (
    EOFError,
    requests.exceptions.ConnectionError,
    requests.exceptions.HTTPError,
)

logger = logging.getLogger(__name__)


@shared_task
def publish_build(build_id: str) -> bool:
    """Publish the build"""
    publisher = get_publisher()

    try:
        pull_build.apply((build_id,), throw=True)
    except PUBLISH_FATAL_EXCEPTIONS:
        logger.error("Build %s failed to pull. Not publishing", f"{build_id}")
        return False

    publisher.publish(Build.from_id(build_id))

    return True


@shared_task
def pull_build(build_id: str) -> None:
    """Pull the build into storage"""
    publisher = get_publisher()
    build = Build.from_id(build_id)

    try:
        publisher.pull(build)
    except Exception as error:
        logger.exception("Failed to pull build %s", build)

        # If this is an error due to 404 response don't retry
        if isinstance(error, requests.exceptions.HTTPError):
            response = getattr(error, "response", None)
            if response is not None and response.status_code == 404:
                publisher.delete(build)
                raise

        if isinstance(error, PULL_RETRYABLE_EXCEPTIONS):
            pull_build.retry(exc=error)
            return

        publisher.delete(build)
        raise

    if Settings.from_environ().ENABLE_PURGE:
        purge_machine.delay(build.machine)


@shared_task
def purge_machine(machine: str) -> None:
    """Purge old builds for machine"""
    publisher = get_publisher()

    publisher.purge(machine)


@shared_task
def delete_build(build_id: str) -> None:
    """Delete the given build from the db"""
    publisher = get_publisher()
    build = Build.from_id(build_id)

    logger.info("Deleting build: %s", build)

    publisher.delete(build)
    logger.info("Deleted build: %s", build)
