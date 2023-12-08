"""Async Jobs for Gentoo Build Publisher"""
from functools import cache
from typing import Protocol

from redis import Redis
from rq import Queue

from gentoo_build_publisher.jobs.celery import CeleryJobs
from gentoo_build_publisher.jobs.rq import RQJobs
from gentoo_build_publisher.settings import Settings


class Error(Exception):
    """Errors for jobs"""


class JobInterfaceNotFoundError(LookupError, Error):
    """Couldn't find you a job"""


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


@cache
def get_jobs(backend_type: str | None = None) -> JobsInterface:
    """Return the appropriate JobsInterface based on the environment

    Looks at Settings.JOBS_BACKEND and return a JobsInterface based on that setting.

    Raise JobInterfaceNotFoundError if the setting is invalid.
    """
    settings = Settings.from_environ()
    if backend_type is None:
        backend_type = settings.JOBS_BACKEND

    match backend_type:
        case "celery":
            return CeleryJobs()
        case "rq":
            queue = Queue(connection=Redis.from_url(settings.REDIS_JOBS_URL))
            return RQJobs(queue)
        case _:
            raise JobInterfaceNotFoundError(settings.JOBS_BACKEND)
