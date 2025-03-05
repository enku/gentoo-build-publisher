"""Tests for gentoo build publisher"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import logging
import unittest

import django.test
from unittest_fixtures import where

logging.basicConfig(handlers=[logging.NullHandler()])


@where(environ={"BUILD_PUBLISHER_RECORDS_BACKEND": "memory"})
class TestCase(unittest.TestCase):
    pass


@where(environ={"BUILD_PUBLISHER_RECORDS_BACKEND": "django"})
class DjangoTestCase(django.test.TestCase):
    pass
