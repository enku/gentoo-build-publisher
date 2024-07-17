"""Tests for gentoo build publisher"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import logging
from functools import wraps

import django.test

from . import setup
from .setup_types import BaseTestCase

logging.basicConfig(handlers=[logging.NullHandler()])


@setup.requires()
class TestCase(BaseTestCase):
    options = {"records_backend": "memory"}


@setup.requires()
class DjangoTestCase(TestCase, django.test.TestCase):
    options = {"records_backend": "django"}


def parametrized(lists_of_args):
    def dec(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs) -> None:
            for list_of_args in lists_of_args:
                name = ",".join(str(i) for i in list_of_args)
                with self.subTest(name):
                    func(self, *args, *list_of_args, **kwargs)

        return wrapper

    return dec
