"""Celery tasks for Gentoo Build Publisher"""
import logging

import requests
import requests.exceptions
from celery import shared_task

from gentoo_build_publisher.build import BuildID
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import Build
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

    build = Build(BuildID(build_id))
    build.publish()

    return True


@shared_task(bind=True)
def pull_build(self, build_id: str) -> None:
    """Pull the build into storage"""
    build = Build(BuildID(build_id))

    try:
        build.pull()
    except PULL_RETRYABLE_EXCEPTIONS as error:
        logger.exception("Failed to pull build %s", build.id)
        if build.record:
            BuildDB.delete(build.id)

        # If this is an error due to 404 response don't retry
        if isinstance(error, requests.exceptions.HTTPError):
            response = getattr(error, "response", None)
            if response and response.status_code == 404:
                raise

        self.retry(exc=error)

        return  # pragma: no cover

    if Settings.from_environ().ENABLE_PURGE:
        purge_build.delay(build.id.name)


@shared_task
def purge_build(build_name: str):
    """Purge old builds for build_name"""
    Build.purge(build_name)


@shared_task
def delete_build(build_id: str):
    """Delete the given build from the db"""
    build = Build(BuildID(build_id))
    logger.info("Deleting build: %s", build_id)

    build.delete()
    logger.info("Deleted build: %s", build_id)
