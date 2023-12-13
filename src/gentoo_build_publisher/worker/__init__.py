"""Async Workers for Gentoo Build Publisher"""
import importlib.metadata
import logging
from functools import cache
from typing import Any, Callable, Protocol

import requests.exceptions

from gentoo_build_publisher.settings import Settings

HTTP_NOT_FOUND = 404
PUBLISH_FATAL_EXCEPTIONS = (requests.exceptions.HTTPError,)
PULL_RETRYABLE_EXCEPTIONS = (
    EOFError,
    requests.exceptions.ConnectionError,
    requests.exceptions.HTTPError,
)

logger = logging.getLogger(__name__)


class WorkerError(Exception):
    """Errors for workers"""


class WorkerNotFoundError(LookupError, WorkerError):
    """Couldn't find you a worker"""


class WorkerInterface(Protocol):
    """Task Queue Interface"""

    def __init__(self, settings: Settings) -> None:
        """Initialize with the given settings"""

    def run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Submit the given function and arguments to the task queue"""

    @classmethod
    def work(cls, settings: Settings) -> Any:
        """Run the task worker for this interface"""


@cache
def Worker(settings: Settings) -> WorkerInterface:  # pylint: disable=invalid-name
    """Return the appropriate WorkerInterface based on the given Settings

    Looks at Settings.WORKER_BACKEND and return a WorkerInterface based on that setting.

    Raise WorkerNotFoundError if the setting is invalid.
    """
    try:
        [backend] = importlib.metadata.entry_points(
            group="gentoo_build_publisher.worker_interface",
            name=settings.WORKER_BACKEND,
        )
    except ValueError:
        raise WorkerNotFoundError(settings.WORKER_BACKEND) from None

    worker_class: type[WorkerInterface] = backend.load()

    return worker_class(settings)
