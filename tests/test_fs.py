# pylint: disable=missing-docstring
import datetime as dt
import shutil

from gentoo_build_publisher import fs
from gentoo_build_publisher.common import Content

from . import TestCase
from .factories import BuildFactory


class EnsureStorageRootTestCase(TestCase):
    def test_creates_dir_if_not_exists(self) -> None:
        shutil.rmtree(self.tmpdir)
        subdirs = ["this", "that", "the other"]

        fs.init_root(self.tmpdir, subdirs)

        self.assertIs(self.tmpdir.is_dir(), True)
        for subdir in subdirs:
            self.assertIs(self.tmpdir.joinpath(subdir).is_dir(), True)


class ExtractTestCase(TestCase):
    def test(self) -> None:
        build = BuildFactory()
        byte_stream = self.artifact_builder.get_artifact(build)

        path = self.tmpdir / "test.tar.gz"
        with open(path, "wb") as outfile:
            fs.save_stream(byte_stream, outfile)

        extracted = self.tmpdir / "extracted"
        fs.extract(path, extracted)

        self.assertIs(extracted.is_dir(), True)

        for content in Content:
            path = extracted / content.value
            self.assertIs(path.is_dir(), True)


class QuickCheckTestCase(TestCase):
    """Tests for the quick_check() helper method"""

    def test(self) -> None:
        timestamp = dt.datetime(2021, 10, 30, 7, 10, 39)
        file1 = str(self.create_file("foo", b"test", timestamp))
        file2 = str(self.create_file("bar", b"xxxx", timestamp))

        result = fs.quick_check(file1, file2)

        self.assertIs(result, True)

    def test_should_return_false_when_file_does_not_exist(self) -> None:
        timestamp = dt.datetime(2021, 10, 30, 7, 10, 39)
        file1 = str(self.create_file("foo", b"test", timestamp))
        file2 = str(self.tmpdir / "bogus")

        result = fs.quick_check(file1, file2)

        self.assertIs(result, False)

    def test_should_return_false_when_mtimes_differ(self) -> None:
        timestamp1 = dt.datetime(2021, 10, 30, 7, 10, 39)
        timestamp2 = dt.datetime(2021, 10, 30, 7, 10, 40)
        file1 = str(self.create_file("foo", b"test", timestamp1))
        file2 = str(self.create_file("bar", b"test", timestamp2))

        result = fs.quick_check(file1, file2)

        self.assertIs(result, False)

    def test_should_return_false_when_sizes_differ(self) -> None:
        timestamp = dt.datetime(2021, 10, 30, 7, 10, 39)
        file1 = str(self.create_file("foo", b"test", timestamp))
        file2 = str(self.create_file("bar", b"tst", timestamp))

        result = fs.quick_check(file1, file2)

        self.assertIs(result, False)


class SymlinkTestCase(TestCase):
    def test_raise_exception_when_symlink_target_exists_and_not_symlink(self) -> None:
        # Given the source and target which is not a symlink
        source = self.create_file("source")
        target = self.create_file("target")

        # Then an exception is raised
        with self.assertRaises(EnvironmentError) as cxt:
            # When we call synlink on source and target
            fs.symlink(str(source), str(target))

        exception = cxt.exception

        self.assertEqual(exception.args, (f"{target} exists but is not a symlink",))
