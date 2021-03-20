"""Celery tasks for Gentoo Build Publisher"""
from celery import shared_task

from gentoo_build_publisher.models import Build


@shared_task(bind=True)
def publish_build(self, build_id: int):
    """Publish the build"""
    build = Build.objects.get(pk=build_id)
    build.task_id = self.request.id
    build.save()
    build.publish()
