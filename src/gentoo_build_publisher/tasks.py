"""Celery task definitions"""
from celery import shared_task

from gentoo_build_publisher.jobs import common


@shared_task
def publish_build(build_id: str) -> bool:
    """Publish the build"""
    return common.publish_build(build_id)


@shared_task
def pull_build(build_id: str, *, note: str | None = None) -> None:
    """Pull the build into storage

    If `note` is given, then the build record will be saved with the given note.
    """
    try:
        common.pull_build(build_id, note=note)
    except Exception as error:
        if (
            isinstance(error, common.PULL_RETRYABLE_EXCEPTIONS)
            and getattr(getattr(error, "response", None), "status_code", None) != 404
        ):
            pull_build.retry(exc=error)
            return
        raise


@shared_task
def purge_machine(machine: str) -> None:
    """Purge old builds for machine"""
    common.purge_machine(machine)


@shared_task
def delete_build(build_id: str) -> None:
    """Delete the given build from the db"""
    common.delete_build(build_id)
