"""Celery tasks for Gentoo Build Publisher"""
from celery import shared_task
from django.utils import timezone

from gentoo_build_publisher.models import BuildModel, KeptBuild
from gentoo_build_publisher.purge import Purger


@shared_task
def publish_build(build_id: int):
    """Publish the build"""
    pull_build.apply((build_id,))
    build_model = BuildModel.objects.get(pk=build_id)
    build_model.publish()


@shared_task(bind=True)
def pull_build(self, build_id: int):
    """Pull the build into storage"""
    build_model = BuildModel.objects.get(pk=build_id)

    if not build_model.storage.pulled(build_model.build):
        build_model.task_id = self.request.id
        build_model.save()
        build_model.storage.pull(build_model.build, build_model.jenkins)
        build_model.completed = timezone.now()
        build_model.save()

    if build_model.settings.ENABLE_PURGE:
        purge_build.delay(build_model.name)


@shared_task
def purge_build(build_name: str):
    """Purge old builds for build_name"""
    builds = BuildModel.objects.filter(name=build_name)
    purger = Purger(builds, key=lambda b: timezone.make_naive(b.submitted))

    for build_model in purger.purge():
        if KeptBuild.keep(build_model) or build_model.storage.published(
            build_model.build
        ):
            continue

        build_model.delete()
