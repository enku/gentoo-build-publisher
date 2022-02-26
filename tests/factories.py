"""Test factories for GBP"""
# pylint: disable=missing-docstring,too-few-public-methods
import factory
from django.utils import timezone

from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.publisher import BuildPublisher
from gentoo_build_publisher.records import BuildRecord, Records
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage
from gentoo_build_publisher.types import Build

from . import MockJenkins


class BuildModelFactory(factory.django.DjangoModelFactory):
    """BuildModel factory"""

    class Meta:
        model = BuildModel

    machine = "babette"
    number = factory.Sequence(lambda n: n)
    submitted = factory.LazyFunction(timezone.now)
    completed = None


class BuildFactory(factory.Factory):
    """Build factory"""

    class Meta:
        model = Build
        inline_args = ("build_id",)

    class Params:
        machine = "babette"
        number = None

    @factory.lazy_attribute_sequence
    def build_id(self, seq):

        if self.number is not None:  # pylint: disable=no-member
            number = self.number  # pylint: disable=no-member
        else:
            number = seq

        return f"{self.machine}.{number}"  # pylint: disable=no-member


class BuildRecordFactory(BuildFactory):
    """BuildRecord Factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = BuildRecord

    submitted = None
    completed = None
    note = None
    logs = None
    keep = False


class BuildPublisherFactory(factory.Factory):
    """BuildPublisher factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = BuildPublisher
        rename = {"build_attr": "build"}

    jenkins = factory.LazyAttribute(
        lambda _: MockJenkins.from_settings(Settings.from_environ())
    )
    storage = factory.LazyAttribute(
        lambda _: Storage.from_settings(Settings.from_environ())
    )
    records = factory.LazyAttribute(
        lambda _: Records.from_settings(Settings.from_environ())
    )
