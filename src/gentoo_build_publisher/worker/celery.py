"""Celery WorkerInterface"""

import base64
import marshal
import types
from typing import Any, Callable

from celery import Celery
from celery.apps.worker import Worker
from django.core import signing

from gentoo_build_publisher.settings import Settings

celery_app = Celery("gentoo_build_publisher")
celery_app.config_from_object("django.conf:settings", namespace="CELERY")


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
        run.delay(signed, *args, **kwargs)

    @classmethod
    def work(cls, settings: Settings) -> None:
        """Run the Celery worker"""
        worker = Worker(  # type: ignore[call-arg]
            app=celery_app,
            concurrency=settings.WORKER_CELERY_CONCURRENCY,
            events=settings.WORKER_CELERY_EVENTS,
            hostname=settings.WORKER_CELERY_HOSTNAME or None,
            loglevel=settings.WORKER_CELERY_LOGLEVEL,
        )
        worker.start()  # type: ignore[attr-defined]


@celery_app.task
def run(signed: str, *args: Any, **kwargs: Any) -> Any:
    """Decrypt signed function and run with the given args"""
    signer = signing.TimestampSigner()
    b64encoded = signer.unsign(signed)
    marshalled = base64.b64decode(b64encoded)
    code = marshal.loads(marshalled)
    func: Callable[..., Any] = types.FunctionType(code, {})

    return func(*args, **kwargs)  # pylint: disable=not-callable
