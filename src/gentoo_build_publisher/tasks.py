"""Celery tasks for Gentoo Build Publisher"""
from __future__ import annotations

import logging

import requests
import requests.exceptions
from celery import shared_task

from .publisher import get_publisher
from .settings import Settings
from .types import Build

PUBLISH_FATAL_EXCEPTIONS = (requests.exceptions.HTTPError,)
PULL_RETRYABLE_EXCEPTIONS = (
    EOFError,
    requests.exceptions.ConnectionError,
    requests.exceptions.HTTPError,
)

logger = logging.getLogger(__name__)


@shared_task
def publish_build(build_id: str):
    """Publish the build"""
    publisher = get_publisher()

    try:
        pull_build.apply((build_id,), throw=True)
    except PUBLISH_FATAL_EXCEPTIONS:
        logger.error("Build %s failed to pull. Not publishing", f"{build_id}")
        return False

    publisher.publish(Build(build_id))

    return True


@shared_task(bind=True)
def pull_build(self, build_id: str) -> None:
    """Pull the build into storage"""
    publisher = get_publisher()
    build = Build(build_id)

    try:
        publisher.pull(build)
    except PULL_RETRYABLE_EXCEPTIONS as error:
        logger.exception("Failed to pull build %s", build)
        if publisher.records.exists(build):
            publisher.records.delete(build)

        # If this is an error due to 404 response don't retry
        if isinstance(error, requests.exceptions.HTTPError):
            response = getattr(error, "response", None)
            if response and response.status_code == 404:
                raise

        self.retry(exc=error)

        return  # pragma: no cover

    if Settings.from_environ().ENABLE_PURGE:
        purge_build.delay(build.machine)


@shared_task
def purge_build(machine: str):
    """Purge old builds for machine"""
    publisher = get_publisher()

    publisher.purge(machine)


@shared_task
def delete_build(build_id: str):
    """Delete the given build from the db"""
    publisher = get_publisher()
    build = Build(build_id)

    logger.info("Deleting build: %s", build)

    publisher.delete(build)
    logger.info("Deleted build: %s", build)
