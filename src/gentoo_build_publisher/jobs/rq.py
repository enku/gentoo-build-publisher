"""RQ JobsInterface"""
from redis import Redis
from rq import Queue

from gentoo_build_publisher import jobs
from gentoo_build_publisher.settings import Settings


class RQJobs:
    """RQ JobsInterface"""

    def __init__(self, settings: Settings) -> None:
        connection = Redis.from_url(settings.REDIS_JOBS_URL)
        self.queue = Queue(connection=connection, is_async=settings.REDIS_JOBS_ASYNC)

    def __repr__(self) -> str:
        return type(self).__name__

    def publish_build(self, build_id: str) -> None:
        """Publish the build"""
        self.queue.enqueue(jobs.publish_build, build_id)

    def pull_build(self, build_id: str, *, note: str | None = None) -> None:
        """Pull the build into storage

        If `note` is given, then the build record will be saved with the given note.
        """
        self.queue.enqueue(jobs.pull_build, build_id, note=note)

    def purge_machine(self, machine: str) -> None:
        """Purge old builds for machine"""
        self.queue.enqueue(jobs.purge_machine, machine)

    def delete_build(self, build_id: str) -> None:
        """Delete the given build from the db"""
        self.queue.enqueue(jobs.delete_build, build_id)
