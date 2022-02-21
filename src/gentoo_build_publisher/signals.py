"""Signal handlers for Gentoo Build Publisher"""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import BuildModel
from .tasks import delete_build


@receiver(post_delete, sender=BuildModel, dispatch_uid="buildmodel-deleted")
def build_model_deleted(
    sender, signal, instance, using, **kwargs
):  # pylint: disable=unused-argument
    """Signal handler for when a BuildModel is deleted"""
    delete_build.delay(str(instance))
