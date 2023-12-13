"""Celery WorkerInterface"""
import base64
import marshal
from typing import Any, Callable

from celery.apps.worker import Worker
from django.core import signing

from gentoo_build_publisher import celery as app
from gentoo_build_publisher import tasks
from gentoo_build_publisher.settings import Settings


class CeleryWorker:
    """Celery WorkerInterface"""

    def __init__(self, _settings: Settings) -> None:
        return

    def __repr__(self) -> str:
        return type(self).__name__

    def run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Submit the given function and arguments to the task queue"""
        signer = signing.TimestampSigner()
        marshalled = marshal.dumps(func.__code__)
        encoded = base64.b64encode(marshalled).decode("ascii")
        signed = signer.sign(encoded)
        tasks.run.delay(signed, *args, **kwargs)

    @classmethod
    def work(cls, settings: Settings) -> None:
        """Run the Celery worker"""
        worker = Worker(  # type: ignore[call-arg]
            app=app,
            concurrency=settings.WORKER_CELERY_CONCURRENCY,
            events=settings.WORKER_CELERY_EVENTS,
            hostname=settings.WORKER_CELERY_HOSTNAME or None,
            loglevel=settings.WORKER_CELERY_LOGLEVEL,
        )
        worker.start()  # type: ignore[attr-defined]
