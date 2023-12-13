"""Sync WorkerInterface

The "sync" WorkerInterface is a simple (testing) WorkerInterface that runs the jobs
synchronously (in process).
"""
import sys
from typing import Any, Callable

from gentoo_build_publisher.settings import Settings


class SyncWorker:
    """A Synchronous WorkerInterface"""

    def __init__(self, _settings: Settings) -> None:
        return

    def __repr__(self) -> str:
        return type(self).__name__

    def run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Submit the given function and arguments to the task queue"""
        func(*args, **kwargs)

    @classmethod
    def work(cls, _settings: Settings) -> None:
        """Do nothing"""
        sys.stderr.write(f"{cls.__name__} has no worker\n")
        raise SystemExit(1)
