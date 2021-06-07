"""Test factories for GBP"""
import factory
from django.utils import timezone

from gentoo_build_publisher import Settings, Storage
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.models import BuildModel

from . import MockJenkins


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
    jenkins = factory.LazyFunction(
        lambda: MockJenkins.from_settings(Settings.from_environ())
    )
    storage = factory.LazyFunction(
        lambda: Storage.from_settings(Settings.from_environ())
    )
