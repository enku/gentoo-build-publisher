"""Celery JobsInterface"""

from gentoo_build_publisher import tasks
from gentoo_build_publisher.settings import Settings


class CeleryJobs:
    """Celery JobsInterface"""

    def __init__(self, _settings: Settings) -> None:
        return

    def __repr__(self) -> str:
        return type(self).__name__

    def publish_build(self, build_id: str) -> None:
        """Publish the build"""
        tasks.publish_build.delay(build_id)

    def pull_build(self, build_id: str, *, note: str | None = None) -> None:
        """Pull the build into storage

        If `note` is given, then the build record will be saved with the given note.
        """
        tasks.pull_build.delay(build_id, note=note)

    def purge_machine(self, machine: str) -> None:
        """Purge old builds for machine"""
        tasks.purge_machine.delay(machine)

    def delete_build(self, build_id: str) -> None:
        """Delete the given build from the db"""
        tasks.delete_build.delay(build_id)
