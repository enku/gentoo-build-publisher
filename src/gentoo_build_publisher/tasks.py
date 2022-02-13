"""Celery tasks for Gentoo Build Publisher"""
import logging

import requests
import requests.exceptions
from celery import shared_task

from gentoo_build_publisher.build import BuildID
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.settings import Settings

PUBLISH_FATAL_EXCEPTIONS = (requests.exceptions.HTTPError,)
PULL_RETRYABLE_EXCEPTIONS = (
    EOFError,
    requests.exceptions.ConnectionError,
    requests.exceptions.HTTPError,
)

logger = logging.getLogger(__name__)


@shared_task
def publish_build(name: str, number: int):
    """Publish the build"""
    try:
        pull_build.apply((name, number), throw=True)
    except PUBLISH_FATAL_EXCEPTIONS:
        logger.error("Build %s failed to pull. Not publishing", f"{name}.{number}")
        return False

    buildman = BuildMan(BuildID.create(name, number))
    buildman.publish()

    return True


@shared_task(bind=True)
def pull_build(self, name: str, number: int) -> None:
    """Pull the build into storage"""
    build_id = BuildID.create(name, number)
    buildman = BuildMan(build_id)

    try:
        buildman.pull()
    except PULL_RETRYABLE_EXCEPTIONS as error:
        logger.exception("Failed to pull build %s", buildman.id)
        if buildman.record:
            BuildDB.delete(buildman.id)

        # If this is an error due to 404 response don't retry
        if isinstance(error, requests.exceptions.HTTPError):
            response = getattr(error, "response", None)
            if response and response.status_code == 404:
                raise

        self.retry(exc=error)

        return

    if Settings.from_environ().ENABLE_PURGE:
        purge_build.delay(name)


@shared_task
def purge_build(build_name: str):
    """Purge old builds for build_name"""
    BuildMan.purge(build_name)


@shared_task
def delete_build(name: str, number: int):
    """Delete the given build from the db"""
    buildman = BuildMan(BuildID.create(name, number))
    logger.info("Deleting build: %s", buildman.id)

    buildman.delete()
    logger.info("Deleted build: %s", buildman.id)
