"""Signal handlers for Gentoo Build Publisher"""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.models import BuildModel


@receiver(post_delete, sender=BuildModel, dispatch_uid="buildmodel-deleted")
def build_model_deleted(
    sender, signal, instance, using, **kwargs
):  # pylint: disable=unused-argument
    """Signal handler for when a BuildModel is deleted"""
    buildman = BuildMan(Build(name=instance.name, number=instance.number))

    buildman.delete()
