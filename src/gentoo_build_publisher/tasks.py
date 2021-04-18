"""Celery tasks for Gentoo Build Publisher"""
from celery import shared_task

from gentoo_build_publisher import Settings
from gentoo_build_publisher.models import BuildModel


@shared_task(bind=True)
def publish_build(self, build_id: int):
    """Publish the build"""
    build_model = BuildModel.objects.get(pk=build_id)
    build_model.task_id = self.request.id
    build_model.save()
    build_model.publish()
    purge_build.delay(build_model.name)


@shared_task
def purge_build(build_name: str):
    """Purge old builds for build_name"""
    settings = Settings.from_environ()
    BuildModel.purge(build_name, settings.PURGE_TO_KEEP)
