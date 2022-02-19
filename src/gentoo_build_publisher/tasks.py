"""Celery tasks for Gentoo Build Publisher"""
from __future__ import annotations

import logging

import requests
import requests.exceptions
from celery import shared_task

from gentoo_build_publisher.build import BuildID
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import BuildPublisher
from gentoo_build_publisher.settings import Settings

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
    try:
        pull_build.apply((build_id,), throw=True)
    except PUBLISH_FATAL_EXCEPTIONS:
        logger.error("Build %s failed to pull. Not publishing", f"{build_id}")
        return False

    build_publisher = BuildPublisher()
    build_publisher.publish(BuildID(build_id))

    return True


@shared_task(bind=True)
def pull_build(self, build_id_str: str) -> None:
    """Pull the build into storage"""
    build_id = BuildID(build_id_str)
    build_publisher = BuildPublisher()

    try:
        build_publisher.pull(build_id)
    except PULL_RETRYABLE_EXCEPTIONS as error:
        logger.exception("Failed to pull build %s", build_id)
        if BuildDB.exists(build_id):
            BuildDB.delete(build_id)

        # If this is an error due to 404 response don't retry
        if isinstance(error, requests.exceptions.HTTPError):
            response = getattr(error, "response", None)
            if response and response.status_code == 404:
                raise

        self.retry(exc=error)

        return  # pragma: no cover

    if Settings.from_environ().ENABLE_PURGE:
        purge_build.delay(build_id.name)


@shared_task
def purge_build(name: str):
    """Purge old builds for build_name"""
    build_publisher = BuildPublisher()

    build_publisher.purge(name)


@shared_task
def delete_build(build_id_str: str):
    """Delete the given build from the db"""
    build_id = BuildID(build_id_str)
    build_publisher = BuildPublisher()

    logger.info("Deleting build: %s", build_id)

    build_publisher.delete(build_id)
    logger.info("Deleted build: %s", build_id)
