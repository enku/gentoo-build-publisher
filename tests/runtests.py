#!/usr/bin/env python
"""Run tests for Gentoo Build Publisher"""
import os
import sys

import django
from django.conf import settings
from django.test.utils import get_runner


def main() -> None:
    """Program entry point"""
    os.environ["DJANGO_SETTINGS_MODULE"] = "settings"
    django.setup()

    tests = sys.argv[1:] or ["."]

    TestRunner = get_runner(settings)  # pylint: disable=invalid-name
    test_runner = TestRunner(failfast=True, verbosity=2)
    failures = test_runner.run_tests(tests)

    sys.exit(bool(failures))


if __name__ == "__main__":
    main()
