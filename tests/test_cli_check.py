"""Tests for the gbpck management command"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import itertools
import re
import shutil
from argparse import ArgumentParser, Namespace

from gbpcli import GBP

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import check
from gentoo_build_publisher.common import Build, Content

from . import TestCase, string_console
from .factories import BuildFactory


class GBPChkTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.gbp = GBP("http://gbp.invalid/")

    def build_with_missing_content(self, content: Content) -> Build:
        build = BuildFactory()
        publisher.pull(build)
        content_path = publisher.storage.get_path(build, content)
        shutil.rmtree(content_path)

        return build

    def orphan_build(self) -> Build:
        build = BuildFactory()
        publisher.pull(build)

        publisher.records.delete(build)

        return build

    def test_empty_system(self) -> None:
        console, stdout, *_ = string_console()
        check.handler(Namespace(), self.gbp, console)

        self.assertEqual(stdout.getvalue(), "0 errors, 0 warnings\n")

    def test_uncompleted_builds_are_skipped(self) -> None:
        build = BuildFactory()
        record = publisher.record(build)
        publisher.records.save(record, completed=None)

        console = string_console()[0]
        exit_status = check.handler(Namespace(), self.gbp, console)

        self.assertEqual(exit_status, 0)

    def test_check_tag_with_dots(self) -> None:
        build = BuildFactory()
        publisher.pull(build)
        publisher.tag(build, "go-1.21.5")

        console, _, stderr = string_console()
        exit_status = check.handler(Namespace(), self.gbp, console)

        self.assertEqual(exit_status, 0, stderr.getvalue())

    def test_check_build_content(self) -> None:
        good_build = BuildFactory()
        publisher.pull(good_build)

        bad_build = self.build_with_missing_content(Content.BINPKGS)

        console, _, err = string_console()
        result = check.check_build_content(console)

        self.assertEqual(result, (1, 0))
        self.assertRegex(
            err.getvalue(), f"^Path missing for {re.escape(str(bad_build))}:"
        )

    def test_check_orphans(self) -> None:
        good_build = BuildFactory()
        publisher.pull(good_build)

        bad_build = self.orphan_build()
        binpkg_path = publisher.storage.get_path(bad_build, Content.BINPKGS)

        console, _, err = string_console()
        result = check.check_orphans(console)

        self.assertEqual(result, (len(Content), 0))
        self.assertRegex(
            err.getvalue(), f"Record missing for {re.escape(str(binpkg_path))}"
        )

    def test_check_orphans_dangling_symlinks(self) -> None:
        build = BuildFactory()
        publisher.pull(build)

        publisher.tag(build, "broken_tag")
        publisher.publish(build)
        # .tag and .publish produce a symlink for each content type
        link_count = len(Content) * 2

        # Delete the build. Symlinks are now broken
        publisher.delete(build)

        console, _, err = string_console()
        result = check.check_orphans(console)

        self.assertEqual(result, (link_count, 0))

        lines = err.getvalue().split("\n")
        for line in lines[:-1]:
            self.assertRegex(line, f"^Broken tag: .*{build.machine}(@broken_tag)?")

    def test_check_inconsistent_tags(self) -> None:
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

        console, _, err = string_console()
        result = check.check_inconsistent_tags(console)

        self.assertEqual(result, (1, 0))
        self.assertRegex(err.getvalue(), '^Tag "larry" has multiple targets: ')

    def test_error_count_in_exit_status(self) -> None:
        for _ in range(2):
            good_build = BuildFactory()
            publisher.pull(good_build)

        for _ in range(3):
            self.orphan_build()

        for _ in range(2):
            self.build_with_missing_content(Content.VAR_LIB_PORTAGE)

        console, _, err = string_console()
        exit_status = check.handler(Namespace(), self.gbp, console)
        self.assertEqual(exit_status, len(Content) * 3 + 2)

        stderr_lines = err.getvalue().split("\n")
        last_error_line = stderr_lines[-2]
        self.assertEqual(last_error_line, "gbp check: Errors were encountered")

    def test_check_tmpdir_nonempty(self) -> None:
        storage = publisher.storage
        root = storage.root
        tmp = root / "tmp"
        dirty_file = tmp / ".keep"
        dirty_file.write_bytes(b"")

        console, _, err = string_console()
        result = check.check_dirty_temp(console)

        self.assertEqual(result, (0, 1))
        self.assertEqual(err.getvalue(), f"Warning: {tmp} is not empty.\n")

    def test_parse_args(self) -> None:
        # here for completeness
        parser = ArgumentParser("gbp")
        check.parse_args(parser)
