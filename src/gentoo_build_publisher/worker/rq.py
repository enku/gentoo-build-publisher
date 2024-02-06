"""RQ WorkerInterface"""

from typing import Any, Callable

from redis import Redis
from rq import Queue, Worker

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

    def run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Submit the given function and arguments to the task queue"""
        self.queue.enqueue(func, *args, **kwargs)

    @classmethod
    def work(cls, settings: Settings) -> None:
        """Run the RQ worker"""
        Worker(
            [settings.WORKER_RQ_QUEUE_NAME],
            connection=Redis.from_url(settings.WORKER_RQ_URL),
            name=settings.WORKER_RQ_NAME or None,
        ).work()
