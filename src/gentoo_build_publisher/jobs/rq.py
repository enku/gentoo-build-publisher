"""RQ JobsInterface"""
from rq import Queue

from gentoo_build_publisher.jobs import common


class RQJobs:
    """RQ JobsInterface"""

    def __init__(self, queue: Queue) -> None:
        self.queue = queue

    def __repr__(self) -> str:
        return type(self).__name__

    def publish_build(self, build_id: str) -> None:
        """Publish the build"""
        self.queue.enqueue(common.publish_build, build_id)

    def pull_build(self, build_id: str, *, note: str | None = None) -> None:
        """Pull the build into storage

        If `note` is given, then the build record will be saved with the given note.
        """
        self.queue.enqueue(common.pull_build, build_id, note=note)

    def purge_machine(self, machine: str) -> None:
        """Purge old builds for machine"""
        self.queue.enqueue(common.purge_machine, machine)

    def delete_build(self, build_id: str) -> None:
        """Delete the given build from the db"""
        self.queue.enqueue(common.delete_build, build_id)
