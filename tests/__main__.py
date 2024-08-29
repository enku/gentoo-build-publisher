#!/usr/bin/env python
"""Run tests for Gentoo Build Publisher"""
import argparse
import os
import sys

import django
from django.conf import settings
from django.test.utils import get_runner


def main() -> None:
    """Program entry point"""
    args = parse_args()
    os.environ["DJANGO_SETTINGS_MODULE"] = args.settings

    # These values are required in order to import the publisher module
    os.environ.setdefault("BUILD_PUBLISHER_JENKINS_BASE_URL", "http://jenkins.invalid/")
    os.environ.setdefault("BUILD_PUBLISHER_STORAGE_PATH", "__testing__")

    django.setup()

    TestRunner = get_runner(settings)  # pylint: disable=invalid-name
    verbosity = 2 if args.verbose else 1
    test_runner = TestRunner(failfast=args.failfast, verbosity=verbosity)
    failures = test_runner.run_tests(args.tests)

    sys.exit(bool(failures))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments"""
    default_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "tests.settings")
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--failfast", action="store_true", default=False)
    parser.add_argument("--settings", default=default_settings)
    parser.add_argument("-v", "--verbose", action="store_true", default=False)
    parser.add_argument("tests", nargs="*", default=["tests"])

    return parser.parse_args()


if __name__ == "__main__":
    main()
