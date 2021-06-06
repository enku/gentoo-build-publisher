"""Celery tasks for Gentoo Build Publisher"""
from celery import shared_task
from django.utils import timezone

from gentoo_build_publisher.diff import diff_notes
from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild
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

        logs = build_model.jenkins.get_build_logs(build_model.build)
        BuildLog.objects.create(build_model=build_model, logs=logs)

        try:
            prev_build = BuildModel.objects.filter(name=build_model.name).order_by(
                "-submitted"
            )[1]
        except IndexError:
            pass
        else:
            binpkgs = build_model.build.Content.BINPKGS
            left = prev_build.storage.get_path(prev_build.build, binpkgs)
            right = build_model.storage.get_path(build_model.build, binpkgs)
            note = diff_notes(str(left), str(right), header="Packages built:\n")

            if note:
                BuildNote.objects.create(build_model=build_model, note=note)

        build_model.completed = timezone.now()
        build_model.save()

    if build_model.settings.ENABLE_PURGE:
        purge_build.delay(build_model.name)


@shared_task
def purge_build(build_name: str):
    """Purge old builds for build_name"""
    builds = BuildModel.objects.filter(name=build_name)
    purger = Purger(builds, key=lambda b: timezone.make_naive(b.submitted))

    for build_model in purger.purge():  # type: BuildModel
        if KeptBuild.keep(build_model) or build_model.storage.published(
            build_model.build
        ):
            continue

        build_model.delete()
