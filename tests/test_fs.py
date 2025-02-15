# pylint: disable=missing-docstring
import datetime as dt
import os
import shutil

import unittest_fixtures as fixture

from gentoo_build_publisher import fs
from gentoo_build_publisher.types import Content

from . import TestCase
from .factories import BuildFactory
from .helpers import create_file


@fixture.requires("tmpdir")
class EnsureStorageRootTestCase(TestCase):
    def test_creates_dir_if_not_exists(self) -> None:
        shutil.rmtree(self.fixtures.tmpdir)
        subdirs = ["this", "that", "the other"]

        fs.init_root(self.fixtures.tmpdir, subdirs)

        self.assertIs(self.fixtures.tmpdir.is_dir(), True)
        for subdir in subdirs:
            self.assertIs(self.fixtures.tmpdir.joinpath(subdir).is_dir(), True)


@fixture.requires("tmpdir", "publisher")
class ExtractTestCase(TestCase):
    def test(self) -> None:
        build = BuildFactory()
        byte_stream = self.fixtures.publisher.jenkins.artifact_builder.get_artifact(
            build
        )

        path = self.fixtures.tmpdir / "test.tar.gz"
        with open(path, "wb") as outfile:
            fs.save_stream(byte_stream, outfile)

        extracted = self.fixtures.tmpdir / "extracted"
        fs.extract(path, extracted)

        self.assertIs(extracted.is_dir(), True)

        for content in Content:
            path = extracted / content.value
            self.assertIs(path.is_dir(), True)


@fixture.requires("tmpdir")
class QuickCheckTestCase(TestCase):
    """Tests for the quick_check() helper method"""

    def test(self) -> None:
        timestamp = dt.datetime(2021, 10, 30, 7, 10, 39)
        file1 = str(create_file(self.fixtures.tmpdir / "foo", b"test", timestamp))
        file2 = str(create_file(self.fixtures.tmpdir / "bar", b"xxxx", timestamp))

        result = fs.quick_check(file1, file2)

        self.assertIs(result, True)

    def test_should_return_false_when_file_does_not_exist(self) -> None:
        timestamp = dt.datetime(2021, 10, 30, 7, 10, 39)
        file1 = str(create_file(self.fixtures.tmpdir / "foo", b"test", timestamp))
        file2 = str(self.fixtures.tmpdir / "bogus")

        result = fs.quick_check(file1, file2)

        self.assertIs(result, False)

    def test_should_return_false_when_mtimes_differ(self) -> None:
        timestamp1 = dt.datetime(2021, 10, 30, 7, 10, 39)
        timestamp2 = dt.datetime(2021, 10, 30, 7, 10, 40)
        file1 = str(create_file(self.fixtures.tmpdir / "foo", b"test", timestamp1))
        file2 = str(create_file(self.fixtures.tmpdir / "bar", b"test", timestamp2))

        result = fs.quick_check(file1, file2)

        self.assertIs(result, False)

    def test_should_return_false_when_sizes_differ(self) -> None:
        timestamp = dt.datetime(2021, 10, 30, 7, 10, 39)
        file1 = str(create_file(self.fixtures.tmpdir / "foo", b"test", timestamp))
        file2 = str(create_file(self.fixtures.tmpdir / "bar", b"tst", timestamp))

        result = fs.quick_check(file1, file2)

        self.assertIs(result, False)


@fixture.requires("tmpdir")
class SymlinkTestCase(TestCase):
    def test_raise_exception_when_symlink_target_exists_and_not_symlink(self) -> None:
        # Given the source and target which is not a symlink
        source = create_file(self.fixtures.tmpdir / "source")
        target = create_file(self.fixtures.tmpdir / "target")

        # Then an exception is raised
        with self.assertRaises(EnvironmentError) as ctx:
            # When we call synlink on source and target
            fs.symlink(str(source), str(target))

        exception = ctx.exception

        self.assertEqual(exception.args, (f"{target} exists but is not a symlink",))


@fixture.requires("tmpdir")
class CheckSymlink(TestCase):
    def test_good_symlink(self) -> None:
        target = create_file(self.fixtures.tmpdir / "target")
        symlink = self.fixtures.tmpdir / "symlink"
        os.symlink(target, symlink)

        self.assertIs(fs.check_symlink(str(symlink), str(target)), True)

    def test_symlink_points_to_different_target(self) -> None:
        target = create_file(self.fixtures.tmpdir / "target")
        symlink = self.fixtures.tmpdir / "symlink"
        os.symlink(target, symlink)
        other = create_file(self.fixtures.tmpdir / "other")

        self.assertIs(fs.check_symlink(str(symlink), str(other)), False)

    def test_dangling_symlink(self) -> None:
        name = self.fixtures.tmpdir / "symlink"
        os.symlink("bogus", name)

        self.assertIs(fs.check_symlink(str(name), "bogus"), False)


@fixture.requires("tmpdir")
class CDTests(TestCase):
    def test(self) -> None:
        tmpdir = str(self.fixtures.tmpdir)

        self.assertNotEqual(os.getcwd(), tmpdir)

        with fs.cd(tmpdir):
            self.assertEqual(os.getcwd(), tmpdir)

        self.assertNotEqual(os.getcwd(), tmpdir)
