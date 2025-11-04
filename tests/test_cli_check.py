"""Tests for the `gbp check` subcommand"""

# pylint: disable=missing-docstring
import shutil

from unittest_fixtures import Fixtures, given

import gbp_testkit.fixtures as testkit
from gbp_testkit import TestCase
from gbp_testkit.factories import BuildFactory
from gentoo_build_publisher.types import Content


@given(testkit.tmpdir, testkit.publisher, testkit.gbpcli)
class GBPChkTestCase(TestCase):
    def test_empty_system(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        fixtures.gbpcli("gbp check")

        self.assertEqual(console.stdout, "$ gbp check\n0 errors, 0 warnings\n")

    def test_uncompleted_builds_are_warnings(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher = fixtures.publisher
        record = publisher.record(build)
        publisher.repo.build_records.save(record, completed=None)

        console = fixtures.console
        exit_status = fixtures.gbpcli("gbp check")

        self.assertEqual(exit_status, 0)
        self.assertEqual(console.stdout, "$ gbp check\n0 errors, 2 warnings\n")
        # 2 warnings because also gbp.json

    def test_check_tag_with_dots(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher = fixtures.publisher
        publisher.pull(build)
        publisher.tag(build, "go-1.21.5")

        console = fixtures.console
        exit_status = fixtures.gbpcli("gbp check")

        self.assertEqual(exit_status, 0, console.stderr)

    def test_error_count_in_exit_status(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        for _ in range(2):
            good_build = BuildFactory()
            publisher.pull(good_build)

        for _ in range(3):
            build = BuildFactory()
            publisher.pull(build)
            publisher.repo.build_records.delete(build)

        for _ in range(2):
            build = BuildFactory()
            publisher.pull(build)
            content_path = publisher.storage.get_path(build, Content.VAR_LIB_PORTAGE)
            shutil.rmtree(content_path)

        console = fixtures.console
        exit_status = fixtures.gbpcli("gbp check")

        self.assertEqual(exit_status, len(Content) * 3 + 2)

        stderr_lines = console.stderr.split("\n")
        last_error_line = stderr_lines[-2]
        self.assertEqual(last_error_line, "gbp check: Errors were encountered")
