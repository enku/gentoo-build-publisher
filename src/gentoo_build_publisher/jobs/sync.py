"""Sync JobsInterface

The "sync" JobsInterface is a simple (testing) JobsInterface that runs the jobs
synchronously (in process).
"""
from gentoo_build_publisher import jobs
from gentoo_build_publisher.settings import Settings


class SyncJobs:
    """A Synchronous JobsInterface"""

    def __init__(self, _settings: Settings) -> None:
        return

    def __repr__(self) -> str:
        return type(self).__name__

    def publish_build(self, build_id: str) -> None:
        """Publish the build"""
        jobs.publish_build(build_id)

    def pull_build(self, build_id: str, *, note: str | None = None) -> None:
        """Pull the build into storage

        If `note` is given, then the build record will be saved with the given note.
        """
        jobs.pull_build(build_id, note=note)

    def purge_machine(self, machine: str) -> None:
        """Purge old builds for machine"""
        jobs.purge_machine(machine)

    def delete_build(self, build_id: str) -> None:
        """Delete the given build from the db"""
        jobs.delete_build(build_id)
