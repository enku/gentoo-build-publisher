"""Celery tasks for Gentoo Build Publisher"""
import logging
import requests
from celery import shared_task
from django.utils import timezone

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.diff import diff_notes
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild
from gentoo_build_publisher.purge import Purger
from gentoo_build_publisher.settings import Settings


@shared_task
def publish_build(name: str, number: int):
    """Publish the build"""
    pull_build.apply((name, number))
    buildman = BuildMan(Build(name=name, number=number))
    buildman.publish()


logger = logging.getLogger(__name__)


@shared_task(bind=True)
def pull_build(self, name: str, number: int):
    """Pull the build into storage"""
    build = Build(name=name, number=number)
    buildman = BuildMan(build)

    try:
        buildman.pull()
    except requests.HTTPError:
        logger.exception("Failed to pull build %s", buildman.build)
        if buildman.model:
            buildman.model.delete()
            return

    assert buildman.model is not None

    buildman.model.task_id = self.request.id
    buildman.model.save()

    logs = buildman.jenkins_build.get_logs()
    BuildLog.objects.create(build_model=buildman.model, logs=logs)

    try:
        prev_build = BuildModel.objects.filter(name=buildman.name).order_by(
            "-submitted"
        )[1]
    except IndexError:
        pass
    else:
        binpkgs = buildman.build.Content.BINPKGS
        left = BuildMan(prev_build).get_path(binpkgs)
        right = buildman.get_path(binpkgs)
        note = diff_notes(str(left), str(right), header="Packages built:\n")

        if note:
            BuildNote.objects.create(build_model=buildman.model, note=note)

    if not buildman.model.completed:
        buildman.model.completed = timezone.now()
        buildman.model.save()

    settings = Settings.from_environ()
    if settings.ENABLE_PURGE:
        purge_build.delay(buildman.name)


@shared_task
def purge_build(build_name: str):
    """Purge old builds for build_name"""
    builds = BuildModel.objects.filter(name=build_name)
    purger = Purger(builds, key=lambda b: timezone.make_naive(b.submitted))

    for build_model in purger.purge():  # type: BuildModel
        if not KeptBuild.keep(build_model) and not BuildMan(build_model).published():
            build_model.delete()
