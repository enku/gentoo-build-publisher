"""Test factories for GBP"""
import factory
from django.utils import timezone

from gentoo_build_publisher.models import Build


class BuildFactory(factory.django.DjangoModelFactory):
    """Build builder"""

    class Meta:
        model = Build

    build_name = "babette"
    build_number = 193
    submitted = factory.LazyFunction(timezone.now)
