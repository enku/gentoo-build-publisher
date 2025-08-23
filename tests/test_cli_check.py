"""Tests for the gbpck management command"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import itertools
import re
import shutil
from argparse import ArgumentParser, Namespace

from unittest_fixtures import Fixtures, given

import gbp_testkit.fixtures as testkit
from gbp_testkit import TestCase
from gbp_testkit.factories import BuildFactory
from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import check
from gentoo_build_publisher.types import Build, Content

# pylint: disable=unused-argument


@given(testkit.tmpdir, testkit.publisher, testkit.gbp, testkit.console)
class GBPChkTestCase(TestCase):
    def build_with_missing_content(self, content: Content) -> Build:
        build = BuildFactory()
        publisher.pull(build)
        content_path = publisher.storage.get_path(build, content)
        shutil.rmtree(content_path)

        return build

    def orphan_build(self) -> Build:
        build = BuildFactory()
        publisher.pull(build)

        publisher.repo.build_records.delete(build)

        return build

    def test_empty_system(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        check.handler(Namespace(), fixtures.gbp, console)

        self.assertEqual(console.stdout, "0 errors, 0 warnings\n")

    def test_uncompleted_builds_are_warnings(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        record = publisher.record(build)
        publisher.repo.build_records.save(record, completed=None)

        console = fixtures.console
        exit_status = check.handler(Namespace(), fixtures.gbp, console)

        self.assertEqual(exit_status, 0)
        self.assertEqual(console.stdout, "0 errors, 2 warnings\n")
        # 2 warnings because also gbp.json

    def test_check_tag_with_dots(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)
        publisher.tag(build, "go-1.21.5")

        console = fixtures.console
        exit_status = check.handler(Namespace(), fixtures.gbp, console)

        self.assertEqual(exit_status, 0, console.stderr)

    def test_check_build_content(self, fixtures: Fixtures) -> None:
        good_build = BuildFactory()
        publisher.pull(good_build)

        bad_build = self.build_with_missing_content(Content.BINPKGS)

        console = fixtures.console
        result = check.check_build_content(console)

        self.assertEqual(result, (1, 0))
        self.assertRegex(
            console.stderr, f"^Path missing for {re.escape(str(bad_build))}:"
        )

    def test_check_orphans(self, fixtures: Fixtures) -> None:
        good_build = BuildFactory()
        publisher.pull(good_build)

        bad_build = self.orphan_build()
        binpkg_path = publisher.storage.get_path(bad_build, Content.BINPKGS)

        console = fixtures.console
        result = check.check_orphans(console)

        self.assertEqual(result, (len(Content), 0))
        self.assertRegex(
            console.stderr, f"Record missing for {re.escape(str(binpkg_path))}"
        )

    def test_check_orphans_dangling_symlinks(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)

        publisher.tag(build, "broken_tag")
        publisher.publish(build)
        # .tag and .publish produce a symlink for each content type
        link_count = len(Content) * 2

        # Delete the build. Symlinks are now broken
        publisher.delete(build)

        console = fixtures.console
        result = check.check_orphans(console)

        self.assertEqual(result, (link_count, 0))

        lines = console.stderr.split("\n")
        for line in lines[:-1]:
            self.assertRegex(line, f"^Broken tag: .*{build.machine}(@broken_tag)?")

    def test_check_inconsistent_tags(self, fixtures: Fixtures) -> None:
        # More than one build is represented by a tag
        good_build = BuildFactory()
        publisher.pull(good_build)

        build1 = BuildFactory(machine="larry")
        publisher.pull(build1)

        build2 = BuildFactory(machine="larry")
        publisher.pull(build2)

        publisher.tag(build2, "good_tag")

        for item, build in zip(Content, itertools.cycle([build1, build2])):
            item_path = publisher.storage.get_path(build, item)
            link = item_path.parent / "larry"
            link.symlink_to(item_path.name)

        console = fixtures.console
        result = check.check_inconsistent_tags(console)

        self.assertEqual(result, (1, 0))
        self.assertRegex(console.stderr, '^Tag "larry" has multiple targets: ')

    def test_error_count_in_exit_status(self, fixtures: Fixtures) -> None:
        for _ in range(2):
            good_build = BuildFactory()
            publisher.pull(good_build)

        for _ in range(3):
            self.orphan_build()

        for _ in range(2):
            self.build_with_missing_content(Content.VAR_LIB_PORTAGE)

        console = fixtures.console
        exit_status = check.handler(Namespace(), fixtures.gbp, console)
        self.assertEqual(exit_status, len(Content) * 3 + 2)

        stderr_lines = console.stderr.split("\n")
        last_error_line = stderr_lines[-2]
        self.assertEqual(last_error_line, "gbp check: Errors were encountered")

    def test_check_tmpdir_nonempty(self, fixtures: Fixtures) -> None:
        storage = publisher.storage
        root = storage.root
        tmp = root / "tmp"
        dirty_file = tmp / ".keep"
        dirty_file.write_bytes(b"")

        console = fixtures.console
        result = check.check_dirty_temp(console)

        self.assertEqual(result, (0, 1))
        self.assertEqual(console.stderr, f"Warning: {tmp} is not empty.\n")

    def test_check_corrupt_gbp_json(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)
        storage = publisher.storage

        gbp_dot_json = storage.get_path(build, Content.BINPKGS) / "gbp.json"
        gbp_dot_json.write_text("xxx", encoding="utf8")

        console = fixtures.console
        errors, warnings = check.check_corrupt_gbp_json(console)

        self.assertEqual((errors, warnings), (1, 0))
        self.assertEqual(console.stderr, f"Error: {gbp_dot_json} is corrupt.\n")

    def test_check_missing_gbp_json(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)
        storage = publisher.storage

        gbp_dot_json = storage.get_path(build, Content.BINPKGS) / "gbp.json"
        gbp_dot_json.unlink()

        console = fixtures.console
        errors, warnings = check.check_corrupt_gbp_json(console)

        self.assertEqual((errors, warnings), (0, 1))
        self.assertEqual(console.stderr, f"Warning: {gbp_dot_json} is missing.\n")

    def test_parse_args(self, fixtures: Fixtures) -> None:
        # here for completeness
        parser = ArgumentParser("gbp")
        check.parse_args(parser)
