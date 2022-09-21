"""Tests for the gbpck management command"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import io
import shutil
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError

from gentoo_build_publisher.types import Content

from . import TestCase
from .factories import BuildFactory


class GBPChkTestCase(TestCase):
    def call_command(self, *args, **kwargs):
        return (call_command("gbpchk", *args, **kwargs),)

    def build_with_missing_content(self, content):
        build = BuildFactory()
        self.publisher.pull(build)
        binpkg_path = self.publisher.storage.get_path(build, content)
        shutil.rmtree(binpkg_path)

        return build

    def orphan_build(self, content):
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

    def test_empty_system(self):
        self.call_command()

    def test_uncompleted_builds_are_skipped(self):
        build = BuildFactory()
        record = self.publisher.record(build)
        self.publisher.records.save(record, completed=None)

        self.call_command()

    def test_build_missing_content(self):
        good_build = BuildFactory()
        self.publisher.pull(good_build)

        bad_build = self.build_with_missing_content(Content.BINPKGS)

        with self.assertRaises(CommandError) as context:
            stderr = io.StringIO()
            self.call_command(stderr=stderr)

        [exit_status] = context.exception.args
        self.assertEqual(exit_status, 1)
        self.assertRegex(stderr.getvalue(), f"^Path missing for {bad_build}:")

    def test_orphan_builds(self):
        good_build = BuildFactory()
        self.publisher.pull(good_build)

        bad_build = self.orphan_build(Content.BINPKGS)
        binpkg_path = self.publisher.storage.get_path(bad_build, Content.BINPKGS)

        with self.assertRaises(CommandError) as context:
            stderr = io.StringIO()
            self.call_command(stderr=stderr)

        [exit_status] = context.exception.args
        self.assertEqual(exit_status, 1)
        self.assertRegex(stderr.getvalue(), f"^Record missing for {binpkg_path}")

    def test_dangling_symlinks(self):
        build = BuildFactory()
        self.publisher.pull(build)

        self.publisher.tag(build, "broken_tag")
        self.publisher.publish(build)
        # .tag and .publish produce a symlink for each conent type
        link_count = len(Content) * 2

        # Delete the build. Symlinks are now broken
        self.publisher.delete(build)

        with self.assertRaises(CommandError) as context:
            stderr = io.StringIO()
            self.call_command(stderr=stderr)

        [exit_status] = context.exception.args
        self.assertEqual(exit_status, link_count)

        lines = stderr.getvalue().split("\n")
        for line in lines[:link_count]:
            self.assertRegex(line, f"^Broken tag: .*{build.machine}(@broken_tag)?")

    def test_error_count_in_exit_status(self):
        for _ in range(2):
            good_build = BuildFactory()
            self.publisher.pull(good_build)

        for _ in range(3):
            self.orphan_build(Content.BINPKGS)

        for _ in range(2):
            self.build_with_missing_content(Content.VAR_LIB_PORTAGE)

        with self.assertRaises(CommandError) as context:
            stderr = io.StringIO()
            self.call_command(stderr=stderr)

        [exit_status] = context.exception.args
        self.assertEqual(exit_status, 5)
