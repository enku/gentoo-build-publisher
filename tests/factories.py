"""Test factories for GBP"""
# pylint: disable=missing-docstring,too-few-public-methods
import factory
from django.utils import timezone

from gentoo_build_publisher.build import BuildID
from gentoo_build_publisher.db import BuildRecord
from gentoo_build_publisher.managers import Build
from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage

from . import MockJenkins


class BuildModelFactory(factory.django.DjangoModelFactory):
    """BuildModel factory"""

    class Meta:
        model = BuildModel

    name = "babette"
    number = factory.Sequence(lambda n: n)
    submitted = factory.LazyFunction(timezone.now)
    completed = None


class BuildIDFactory(factory.Factory):
    """BuildID factory"""

    class Meta:
        model = BuildID
        inline_args = ("build_id",)

    class Params:
        name = "babette"

    @factory.lazy_attribute_sequence
    def build_id(self, seq):
        return f"{self.name}.{seq}"  # pylint: disable=no-member


class BuildRecordFactory(factory.Factory):
    """BuildDB Factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = BuildRecord

    build_id = factory.SubFactory(BuildIDFactory)
    submitted = None
    completed = None
    note = None
    logs = None
    keep = False


class BuildFactory(factory.Factory):
    """Build factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = Build
        rename = {"build_attr": "build"}

    build_attr = factory.SubFactory(BuildRecordFactory)
    jenkins = factory.LazyAttribute(
        lambda _: MockJenkins.from_settings(Settings.from_environ())
    )
    storage = factory.LazyAttribute(
        lambda _: Storage.from_settings(Settings.from_environ())
    )

    @classmethod
    def create(cls, *args, **kwargs) -> Build:
        build = super().create(*args, **kwargs)

        if not build.record:
            build.record = BuildRecordFactory.create(build_id=build.id)

        build.save_record()

        return build
