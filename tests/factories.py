"""Test factories for GBP"""
import factory
from django.utils import timezone

from gentoo_build_publisher.models import BuildModel


class BuildModelFactory(factory.django.DjangoModelFactory):
    """BuildModel factory"""

    class Meta:
        model = BuildModel

    name = "babette"
    number = 193
    submitted = factory.LazyFunction(timezone.now)