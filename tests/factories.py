"""Test factories for GBP"""
import factory
from django.utils import timezone

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import StorageBuild

from . import MockJenkinsBuild


class BuildModelFactory(factory.django.DjangoModelFactory):
    """BuildModel factory"""

    class Meta:
        model = BuildModel

    name = "babette"
    number = factory.Sequence(lambda n: n)
    submitted = factory.LazyFunction(timezone.now)


class BuildDBFactory(factory.Factory):
    """BuildDB Factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = BuildDB

    build_model = factory.LazyFunction(BuildModelFactory.create)


class BuildManFactory(factory.Factory):
    """BuildMan factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = BuildMan
        rename = {"build_attr": "build"}

    build_attr = factory.LazyFunction(BuildDBFactory.create)
    jenkins_build = factory.LazyAttribute(
        lambda obj: MockJenkinsBuild.from_settings(
            obj.build_attr, Settings.from_environ()
        )
    )
    storage_build = factory.LazyAttribute(
        lambda obj: StorageBuild.from_settings(
            Build(obj.build_attr.name, obj.build_attr.number), Settings.from_environ()
        )
    )
