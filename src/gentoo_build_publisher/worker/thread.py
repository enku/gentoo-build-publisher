"""Thread worker

Basically this is like the "sync" worker but instead throws the function into a thread.
"""
import threading
from typing import Any, Callable

from gentoo_build_publisher.settings import Settings


class ThreadWorker:
    """A WorkerInterface implementation using threads"""

    def __init__(self, _settings: Settings) -> None:
        """Initialize with the given settings"""

    def __repr__(self) -> str:
        return type(self).__name__

    def run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Run the given function in a thread"""
        # Note we have to do this for tests, unfortnately, because the settings that is
        # passed in __init__ is going to be different by the time .run() is called (due
        # to mocking)
        settings = Settings.from_environ()

        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.start()

        # If we're running in test mode, we want to block
        if settings.WORKER_THREAD_WAIT:
            thread.join()

    @classmethod
    def work(cls, settings: Settings) -> Any:
        """Run the task worker for this interface"""
        # We don't actually have to do anything here
