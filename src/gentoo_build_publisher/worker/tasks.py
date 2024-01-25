"""
Common functions for async workers

These are basically functions that are wrapped by WorkerInterface implementations.  The
core logic is here and the WorkerInterface implementations provide the backend-specific
bits like submitting to the task queue, retries, etc.
"""

# There should not be any top-level imports here as all tasks will be run by the worker
# with no globals
# pylint: disable=import-outside-toplevel,redefined-outer-name,import-self


def publish_build(build_id: str) -> bool:
    """Publish the build"""
    from gentoo_build_publisher import publisher
    from gentoo_build_publisher.common import Build
    from gentoo_build_publisher.worker import PUBLISH_FATAL_EXCEPTIONS, logger
    from gentoo_build_publisher.worker.tasks import pull_build

    try:
        pull_build(build_id, note=None, tags=None)
    except PUBLISH_FATAL_EXCEPTIONS:
        logger.error("Build %s failed to pull. Not publishing", f"{build_id}")
        return False

    publisher.publish(Build.from_id(build_id))

    return True


def pull_build(build_id: str, *, note: str | None, tags: list[str] | None) -> None:
    """Pull the build into storage

    If `note` is given, then the build record will be saved with the given note.
    """
    from gentoo_build_publisher import publisher
    from gentoo_build_publisher.common import Build
    from gentoo_build_publisher.settings import Settings
    from gentoo_build_publisher.worker import logger
    from gentoo_build_publisher.worker.tasks import purge_machine

    build = Build.from_id(build_id)

    try:
        publisher.pull(build, note=note, tags=tags)
    except Exception:
        logger.exception("Failed to pull build %s", build)
        publisher.delete(build)
        raise

    if Settings.from_environ().ENABLE_PURGE:
        purge_machine(build.machine)


def purge_machine(machine: str) -> None:
    """Purge old builds for machine"""
    from gentoo_build_publisher import publisher

    publisher.purge(machine)


def delete_build(build_id: str) -> None:
    """Delete the given build from the db"""
    from gentoo_build_publisher import publisher
    from gentoo_build_publisher.common import Build
    from gentoo_build_publisher.worker import logger

    build = Build.from_id(build_id)

    logger.info("Deleting build: %s", build)

    publisher.delete(build)
    logger.info("Deleted build: %s", build)
