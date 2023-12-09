"""Celery task definitions"""
from celery import shared_task

from gentoo_build_publisher import worker


@shared_task
def publish_build(build_id: str) -> bool:
    """Publish the build"""
    return worker.publish_build(build_id)


@shared_task
def pull_build(build_id: str, *, note: str | None = None) -> None:
    """Pull the build into storage

    If `note` is given, then the build record will be saved with the given note.
    """
    try:
        worker.pull_build(build_id, note=note)
    except Exception as error:
        if (
            isinstance(error, worker.PULL_RETRYABLE_EXCEPTIONS)
            and getattr(getattr(error, "response", None), "status_code", None) != 404
        ):
            pull_build.retry(exc=error)
            return
        raise


@shared_task
def purge_machine(machine: str) -> None:
    """Purge old builds for machine"""
    worker.purge_machine(machine)


@shared_task
def delete_build(build_id: str) -> None:
    """Delete the given build from the db"""
    worker.delete_build(build_id)
