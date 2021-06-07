"""Test factories for GBP"""
import factory
from django.utils import timezone

from gentoo_build_publisher import Settings, StorageBuild
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.models import BuildModel

from . import MockJenkinsBuild


class BuildModelFactory(factory.django.DjangoModelFactory):
    """BuildModel factory"""

    class Meta:
        model = BuildModel

    name = "babette"
    number = factory.Sequence(lambda n: n)
    submitted = factory.LazyFunction(timezone.now)


class BuildManFactory(factory.Factory):
    """BuildMan factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = BuildMan
        rename = {"build_attr": "build"}

    build_attr = factory.LazyFunction(BuildModelFactory.create)
    jenkins_build = factory.LazyAttribute(
        lambda obj: MockJenkinsBuild.from_settings(
            obj.build_attr, Settings.from_environ()
        )
    )
    storage_build = factory.LazyAttribute(
        lambda obj: StorageBuild.from_settings(obj.build_attr, Settings.from_environ())
    )
