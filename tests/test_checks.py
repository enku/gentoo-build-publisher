"""Tests for Gentoo Build Publisher checks"""

# pylint: disable=missing-docstring

import itertools
import re
import shutil
from unittest import TestCase

from unittest_fixtures import Fixtures, given

from gbp_testkit import fixtures as testkit
from gbp_testkit.factories import BuildFactory
from gentoo_build_publisher import checks
from gentoo_build_publisher.build_publisher import BuildPublisher
from gentoo_build_publisher.types import Build, Content


@given(testkit.console, testkit.publisher)
class BuildContentTests(TestCase):
    def test_build_content(self, fixtures: Fixtures) -> None:
        good_build = BuildFactory()
        publisher = fixtures.publisher
        publisher.pull(good_build)

        bad_build = build_with_missing_content(Content.BINPKGS, publisher)

        console = fixtures.console
        result = checks.build_content(console)

        self.assertEqual(result, (1, 0))
        self.assertRegex(
            console.stderr, f"^Path missing for {re.escape(str(bad_build))}:"
        )


@given(testkit.console, testkit.publisher)
class MissingGBPJsonTests(TestCase):
    def test_missing_gbp_json(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher = fixtures.publisher
        publisher.pull(build)
        storage = publisher.storage

        gbp_dot_json = storage.get_path(build, Content.BINPKGS) / "gbp.json"
        gbp_dot_json.unlink()

        console = fixtures.console
        errors, warnings = checks.corrupt_gbp_json(console)

        self.assertEqual((errors, warnings), (0, 1))
        self.assertEqual(console.stderr, f"Warning: {gbp_dot_json} is missing.\n")

    def test_check_corrupt_gbp_json(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher = fixtures.publisher
        publisher.pull(build)
        storage = publisher.storage

        gbp_dot_json = storage.get_path(build, Content.BINPKGS) / "gbp.json"
        gbp_dot_json.write_text("xxx", encoding="utf8")

        console = fixtures.console
        errors, warnings = checks.corrupt_gbp_json(console)

        self.assertEqual((errors, warnings), (1, 0))
        self.assertEqual(console.stderr, f"Error: {gbp_dot_json} is corrupt.\n")


@given(testkit.console, testkit.publisher)
class InconsistentTagsTests(TestCase):
    def test_inconsistent_tags(self, fixtures: Fixtures) -> None:
        # More than one build is represented by a tag
        good_build = BuildFactory()
        publisher = fixtures.publisher
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
        result = checks.inconsistent_tags(console)

        self.assertEqual(result, (1, 0))
        self.assertRegex(console.stderr, '^Tag "larry" has multiple targets: ')


@given(testkit.console, testkit.publisher)
class OrphansTests(TestCase):
    def test_check_orphans(self, fixtures: Fixtures) -> None:
        good_build = BuildFactory()
        publisher = fixtures.publisher
        publisher.pull(good_build)

        bad_build = orphan_build(publisher)
        binpkg_path = publisher.storage.get_path(bad_build, Content.BINPKGS)

        console = fixtures.console
        result = checks.orphans(console)

        self.assertEqual(result, (len(Content), 0))
        self.assertRegex(
            console.stderr, f"Record missing for {re.escape(str(binpkg_path))}"
        )

    def test_check_orphans_dangling_symlinks(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher = fixtures.publisher
        publisher.pull(build)

        publisher.tag(build, "broken_tag")
        publisher.publish(build)
        # .tag and .publish produce a symlink for each content type
        link_count = len(Content) * 2

        # Delete the build. Symlinks are now broken
        publisher.delete(build)

        console = fixtures.console
        result = checks.orphans(console)

        self.assertEqual(result, (link_count, 0))

        lines = console.stderr.split("\n")
        for line in lines[:-1]:
            self.assertRegex(line, f"^Broken tag: .*{build.machine}(@broken_tag)?")


@given(testkit.console, testkit.publisher)
class DirtyTempTests(TestCase):
    def test_check_tmpdir_nonempty(self, fixtures: Fixtures) -> None:
        publisher = fixtures.publisher
        storage = publisher.storage
        tmp = storage.temp
        dirty_file = tmp / ".keep"
        dirty_file.write_bytes(b"")

        console = fixtures.console
        result = checks.dirty_temp(console)

        self.assertEqual(result, (0, 1))
        self.assertEqual(console.stderr, f"Warning: {tmp} is not empty.\n")


def build_with_missing_content(content: Content, publisher: BuildPublisher) -> Build:
    build = BuildFactory()
    publisher.pull(build)
    content_path = publisher.storage.get_path(build, content)
    shutil.rmtree(content_path)

    return build


def orphan_build(publisher: BuildPublisher) -> Build:
    build = BuildFactory()
    publisher.pull(build)

    publisher.repo.build_records.delete(build)

    return build
