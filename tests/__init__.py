"""Tests for gentoo build publisher"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import logging

import django.test
import unittest_fixtures as fixture

logging.basicConfig(handlers=[logging.NullHandler()])


@fixture.requires()
class TestCase(fixture.BaseTestCase):
    options = {"records_backend": "memory"}


@fixture.requires()
class DjangoTestCase(TestCase, django.test.TestCase):
    options = {"records_backend": "django"}
