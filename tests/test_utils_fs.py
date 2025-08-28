# pylint: disable=missing-docstring
import datetime as dt
import os
import shutil

from unittest_fixtures import Fixtures, given

import gbp_testkit.fixtures as testkit
from gbp_testkit import TestCase
from gbp_testkit.factories import BuildFactory
from gbp_testkit.helpers import create_file
from gentoo_build_publisher import publisher
from gentoo_build_publisher.types import Content
from gentoo_build_publisher.utils import fs

TIMESTAMP = dt.datetime(2021, 10, 30, 7, 10, 39)


@given(testkit.tmpdir)
class EnsureStorageRootTestCase(TestCase):
    def test_creates_dir_if_not_exists(self, fixtures: Fixtures) -> None:
        shutil.rmtree(fixtures.tmpdir)
        subdirs = ["this", "that", "the other"]

        fs.init_root(fixtures.tmpdir, subdirs)

        self.assertIs(fixtures.tmpdir.is_dir(), True)
        for subdir in subdirs:
            self.assertIs(fixtures.tmpdir.joinpath(subdir).is_dir(), True)


@given(testkit.tmpdir, testkit.publisher)
class ExtractTestCase(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        byte_stream = publisher.jenkins.artifact_builder.get_artifact(build)

        path = fixtures.tmpdir / "test.tar.gz"
        with open(path, "wb") as outfile:
            fs.save_stream(byte_stream, outfile)

        extracted = fixtures.tmpdir / "extracted"
        fs.extract(path, extracted)

        self.assertIs(extracted.is_dir(), True)

        for content in Content:
            path = extracted / content.value
            self.assertIs(path.is_dir(), True)


@given(file=lambda f: str(create_file(f.tmpdir / "foo", b"test", TIMESTAMP)))
@given(testkit.tmpdir)
class QuickCheckTestCase(TestCase):
    """Tests for the quick_check() helper method"""

    def test(self, fixtures: Fixtures) -> None:
        other = str(create_file(fixtures.tmpdir / "bar", b"xxxx", TIMESTAMP))

        result = fs.quick_check(fixtures.file, other)

        self.assertIs(result, True)

    def test_should_return_false_when_file_does_not_exist(
        self, fixtures: Fixtures
    ) -> None:
        other = str(fixtures.tmpdir / "bogus")

        result = fs.quick_check(fixtures.file, other)

        self.assertIs(result, False)

    def test_should_return_false_when_mtimes_differ(self, fixtures: Fixtures) -> None:
        timestamp2 = dt.datetime(2021, 10, 30, 7, 10, 40)
        other = str(create_file(fixtures.tmpdir / "bar", b"test", timestamp2))

        result = fs.quick_check(fixtures.file, other)

        self.assertIs(result, False)

    def test_should_return_false_when_sizes_differ(self, fixtures: Fixtures) -> None:
        other = str(create_file(fixtures.tmpdir / "bar", b"tst", TIMESTAMP))

        result = fs.quick_check(fixtures.file, other)

        self.assertIs(result, False)


@given(testkit.tmpdir)
class SymlinkTestCase(TestCase):
    def test_raise_exception_when_symlink_target_exists_and_not_symlink(
        self, fixtures: Fixtures
    ) -> None:
        # Given the source and target which is not a symlink
        source = create_file(fixtures.tmpdir / "source")
        target = create_file(fixtures.tmpdir / "target")

        # Then an exception is raised
        with self.assertRaises(EnvironmentError) as ctx:
            # When we call synlink on source and target
            fs.symlink(str(source), str(target))

        exception = ctx.exception

        self.assertEqual(exception.args, (f"{target} exists but is not a symlink",))


@given(symlink=lambda fixtures: fixtures.tmpdir / "symlink")
@given(target=lambda fixtures: create_file(fixtures.tmpdir / "target"))
@given(testkit.tmpdir)
class CheckSymlink(TestCase):
    def test_good_symlink(self, fixtures: Fixtures) -> None:
        os.symlink(fixtures.target, fixtures.symlink)

        self.assertIs(fs.check_symlink(str(fixtures.symlink), str(fixtures.target)), True)

    def test_symlink_points_to_different_target(self, fixtures: Fixtures) -> None:
        os.symlink(fixtures.target, fixtures.symlink)
        other = create_file(fixtures.tmpdir / "other")

        self.assertIs(fs.check_symlink(str(fixtures.symlink), str(other)), False)

    def test_dangling_symlink(self, fixtures: Fixtures) -> None:
        os.symlink("bogus", fixtures.symlink)

        self.assertIs(fs.check_symlink(str(fixtures.symlink), "bogus"), False)


@given(testkit.tmpdir)
class CDTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        tmpdir = str(fixtures.tmpdir)

        self.assertNotEqual(os.getcwd(), tmpdir)

        with fs.cd(tmpdir):
            self.assertEqual(os.getcwd(), tmpdir)

        self.assertNotEqual(os.getcwd(), tmpdir)


class ImportFromRootTests(TestCase):
    def test(self) -> None:
        # pylint: disable=import-outside-toplevel,no-name-in-module
        from gentoo_build_publisher import fs as root_fs

        self.assertIs(fs, root_fs)
