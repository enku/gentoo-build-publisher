"""Test factories for GBP"""
import factory
from django.utils import timezone

from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage

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

    build_model = factory.SubFactory(BuildModelFactory)


class BuildManFactory(factory.Factory):
    """BuildMan factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = BuildMan
        rename = {"build_attr": "build"}

    build_attr = factory.SubFactory(BuildDBFactory)
    jenkins_build = factory.LazyAttribute(
        lambda obj: MockJenkinsBuild.from_settings(
            obj.build_attr, Settings.from_environ()
        )
    )
    storage = factory.LazyAttribute(
        lambda _: Storage.from_settings(Settings.from_environ())
    )
