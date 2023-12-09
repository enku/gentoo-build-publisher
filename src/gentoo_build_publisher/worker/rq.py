"""RQ WorkerInterface"""
from redis import Redis
from rq import Queue, Worker

from gentoo_build_publisher import worker
from gentoo_build_publisher.settings import Settings


class RQWorker:
    """RQ WorkerInterface"""

    def __init__(self, settings: Settings) -> None:
        self.queue = Queue(
            name=settings.WORKER_RQ_QUEUE_NAME,
            connection=Redis.from_url(settings.WORKER_RQ_URL),
            is_async=settings.WORKER_RQ_ASYNC,
        )

    def __repr__(self) -> str:
        return type(self).__name__

    def publish_build(self, build_id: str) -> None:
        """Publish the build"""
        self.queue.enqueue(worker.publish_build, build_id)

    def pull_build(self, build_id: str, *, note: str | None = None) -> None:
        """Pull the build into storage

        If `note` is given, then the build record will be saved with the given note.
        """
        self.queue.enqueue(worker.pull_build, build_id, note=note)

    def purge_machine(self, machine: str) -> None:
        """Purge old builds for machine"""
        self.queue.enqueue(worker.purge_machine, machine)

    def delete_build(self, build_id: str) -> None:
        """Delete the given build from the db"""
        self.queue.enqueue(worker.delete_build, build_id)

    @classmethod
    def work(cls, settings: Settings) -> None:
        """Run the RQ worker"""
        Worker(
            [settings.WORKER_RQ_QUEUE_NAME],
            connection=Redis.from_url(settings.WORKER_RQ_URL),
            name=settings.WORKER_RQ_NAME or None,
        ).work()
