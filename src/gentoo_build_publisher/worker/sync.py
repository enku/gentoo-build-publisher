"""Sync WorkerInterface

The "sync" WorkerInterface is a simple (testing) WorkerInterface that runs the jobs
synchronously (in process).
"""
import sys

from gentoo_build_publisher import worker
from gentoo_build_publisher.settings import Settings


class SyncWorker:
    """A Synchronous WorkerInterface"""

    def __init__(self, _settings: Settings) -> None:
        return

    def __repr__(self) -> str:
        return type(self).__name__

    def publish_build(self, build_id: str) -> None:
        """Publish the build"""
        worker.publish_build(build_id)

    def pull_build(self, build_id: str, *, note: str | None = None) -> None:
        """Pull the build into storage

        If `note` is given, then the build record will be saved with the given note.
        """
        worker.pull_build(build_id, note=note)

    def purge_machine(self, machine: str) -> None:
        """Purge old builds for machine"""
        worker.purge_machine(machine)

    def delete_build(self, build_id: str) -> None:
        """Delete the given build from the db"""
        worker.delete_build(build_id)

    @classmethod
    def work(cls, _settings: Settings) -> None:
        """Do nothing"""
        sys.stderr.write(f"{cls.__name__} has no worker\n")
        raise SystemExit(1)
