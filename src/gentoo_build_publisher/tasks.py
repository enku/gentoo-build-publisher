"""Celery tasks for Gentoo Build Publisher"""
from celery import shared_task

from gentoo_build_publisher.models import BuildModel


@shared_task(bind=True)
def publish_build(self, build_id: int):
    """Publish the build"""
    build_model = BuildModel.objects.get(pk=build_id)
    build_model.task_id = self.request.id
    build_model.save()
    build_model.publish()
