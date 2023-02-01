"""Tests for the gbpck management command"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import io
import itertools
import re
import shutil
from argparse import ArgumentParser, Namespace
from pathlib import Path
from unittest import mock

from gbpcli import GBP
from rich.console import Console

from gentoo_build_publisher import check
from gentoo_build_publisher.types import Build, Content

from . import TestCase
from .factories import BuildFactory


class GBPChkTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.console = mock.MagicMock(spec=Console)
        self.gbp = GBP("http://gbp.invalid/")

    def build_with_missing_content(self, content: Content) -> Build:
        build = BuildFactory()
        self.publisher.pull(build)
        binpkg_path = self.publisher.storage.get_path(build, content)
        shutil.rmtree(binpkg_path)

        return build

    def orphan_build(self, content: Content) -> Build:
        build = BuildFactory()
        self.publisher.pull(build)

        # There is a post-signal for django models so that if I delete the model it will
        # delete the storage, but for this test I want to keep the storage, so let's
        # move something out of the way first
        binpkg_path = self.publisher.storage.get_path(build, content)
        tmp_name = str(binpkg_path) + ".tmp"
        binpkg_path.rename(tmp_name)
        self.publisher.records.delete(build)

        # Rename it back
        Path(tmp_name).rename(str(binpkg_path))

        return build

    def test_empty_system(self) -> None:
        check.handler(Namespace(), self.gbp, self.console)

    def test_uncompleted_builds_are_skipped(self) -> None:
        build = BuildFactory()
        record = self.publisher.record(build)
        self.publisher.records.save(record, completed=None)

        exit_status = check.handler(Namespace(), self.gbp, self.console)

        self.assertEqual(exit_status, 0)

    def test_check_build_content(self) -> None:
        good_build = BuildFactory()
        self.publisher.pull(good_build)

        bad_build = self.build_with_missing_content(Content.BINPKGS)
        errorf = io.StringIO()

        errors = check.check_build_content(self.publisher, errorf)

        self.assertEqual(errors, 1)
        self.assertRegex(
            errorf.getvalue(), f"^Path missing for {re.escape(str(bad_build))}:"
        )

    def test_check_orphans(self) -> None:
        good_build = BuildFactory()
        self.publisher.pull(good_build)

        bad_build = self.orphan_build(Content.BINPKGS)
        binpkg_path = self.publisher.storage.get_path(bad_build, Content.BINPKGS)

        errorf = io.StringIO()
        errors = check.check_orphans(self.publisher, errorf)

        self.assertEqual(errors, 1)
        self.assertRegex(
            errorf.getvalue(), f"^Record missing for {re.escape(str(binpkg_path))}"
        )

    def test_check_orphans_dangling_symlinks(self) -> None:
        build = BuildFactory()
        self.publisher.pull(build)

        self.publisher.tag(build, "broken_tag")
        self.publisher.publish(build)
        # .tag and .publish produce a symlink for each conent type
        link_count = len(Content) * 2

        # Delete the build. Symlinks are now broken
        self.publisher.delete(build)

        errorf = io.StringIO()
        errors = check.check_orphans(self.publisher, errorf)

        self.assertEqual(errors, link_count)

        lines = errorf.getvalue().split("\n")
        for line in lines[:-1]:
            self.assertRegex(line, f"^Broken tag: .*{build.machine}(@broken_tag)?")

    def test_check_inconsistent_tags(self) -> None:
        # More than one build is represented by a tag
        good_build = BuildFactory()
        self.publisher.pull(good_build)

        build1 = BuildFactory(machine="larry")
        self.publisher.pull(build1)

        build2 = BuildFactory(machine="larry")
        self.publisher.pull(build2)

        self.publisher.tag(build2, "good_tag")

        for item, build in zip(Content, itertools.cycle([build1, build2])):
            item_path = self.publisher.storage.get_path(build, item)
            link = item_path.parent / "larry"
            link.symlink_to(item_path.name)

        errorf = io.StringIO()
        errors = check.check_inconsistent_tags(self.publisher, errorf)

        self.assertEqual(errors, 1)
        self.assertRegex(errorf.getvalue(), '^Tag "larry" has multiple targets: ')

    def test_error_count_in_exit_status(self) -> None:
        for _ in range(2):
            good_build = BuildFactory()
            self.publisher.pull(good_build)

        for _ in range(3):
            self.orphan_build(Content.BINPKGS)

        for _ in range(2):
            self.build_with_missing_content(Content.VAR_LIB_PORTAGE)

        errorf = io.StringIO()
        exit_status = check.handler(Namespace(), self.gbp, self.console, errorf)
        self.assertEqual(exit_status, 5)

        stderr_lines = errorf.getvalue().split("\n")
        last_error_line = stderr_lines[-2]
        self.assertEqual(last_error_line, "gbp check: Errors were encountered")

    def test_parse_args(self) -> None:
        # here for completeness
        parser = ArgumentParser("gbp")
        check.parse_args(parser)
