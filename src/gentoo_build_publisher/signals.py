"""Signal handlers for Gentoo Build Publisher"""
from django.db.models.signals import ModelSignal, post_delete
from django.dispatch import receiver

from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.tasks import delete_build


@receiver(post_delete, sender=BuildModel, dispatch_uid="buildmodel-deleted")
def build_model_deleted(
    sender: type[BuildModel], signal: ModelSignal, instance: BuildModel, using: str
) -> None:
    """Signal handler for when a BuildModel is deleted"""
    # pylint: disable=unused-argument
    delete_build.delay(str(instance))
