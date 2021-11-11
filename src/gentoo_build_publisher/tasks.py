"""Celery tasks for Gentoo Build Publisher"""
import logging

import requests
import requests.exceptions
from celery import shared_task

from gentoo_build_publisher.build import Build
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
        logger.error("Build %s/%s failed to pull. Not publishing", name, number)
        return False

    buildman = BuildMan(Build(name=name, number=number))
    buildman.publish()

    return True


@shared_task(bind=True)
def pull_build(self, name: str, number: int):
    """Pull the build into storage"""
    build = Build(name=name, number=number)
    buildman = BuildMan(build)

    try:
        buildman.pull()
    except PULL_RETRYABLE_EXCEPTIONS as error:
        logger.exception("Failed to pull build %s", buildman.build)
        if buildman.db:
            buildman.db.delete()

        # If this is an error due to 404 response don't retry
        if isinstance(error, requests.exceptions.HTTPError):
            response = getattr(error, "response", None)
            if response and response.status_code == 404:
                raise

        self.retry(exc=error)

        return

    if Settings.from_environ().ENABLE_PURGE:
        purge_build.delay(buildman.name)


@shared_task
def purge_build(build_name: str):
    """Purge old builds for build_name"""
    BuildMan.purge(build_name)


@shared_task
def delete_build(name: str, number: int):
    """Delete the given build from the db"""
    build = Build(name=name, number=number)
    logger.info("Deleting build: %s", build)

    buildman = BuildMan(build)
    buildman.delete()
    logger.info("Deleted build: %s", build)
