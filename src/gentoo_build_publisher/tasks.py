"""Celery tasks for Gentoo Build Publisher"""
import logging

import requests
from celery import shared_task
from django.utils import timezone

from gentoo_build_publisher.build import Build, Content
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.diff import diff_notes
from gentoo_build_publisher.managers import BuildMan
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
        if buildman.db:
            buildman.db.delete()

        return

    assert buildman.db is not None

    logs = buildman.jenkins_build.get_logs()

    buildman.db.task_id = self.request.id
    buildman.db.logs = logs
    buildman.db.save()

    prev_build = BuildDB.previous_build(buildman.db)

    if prev_build is not None:
        binpkgs = Content.BINPKGS
        left = BuildMan(prev_build).get_path(binpkgs)
        right = buildman.get_path(binpkgs)
        note = diff_notes(str(left), str(right), header="Packages built:\n")

        if note:
            buildman.db.note = note

    buildman.db.completed = timezone.now()
    buildman.db.save()

    settings = Settings.from_environ()
    if settings.ENABLE_PURGE:
        purge_build.delay(buildman.name)


@shared_task
def purge_build(build_name: str):
    """Purge old builds for build_name"""
    build_dbs = BuildDB.builds(name=build_name)
    purger = Purger(build_dbs, key=lambda b: timezone.make_naive(b.submitted))

    for build_db in purger.purge():  # type: BuildDB
        if not build_db.keep and not BuildMan(build_db).published():
            buildman = BuildMan(build_db)
            buildman.delete()
