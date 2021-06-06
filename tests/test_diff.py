"""Tests for the diff module"""
# pylint: disable=missing-function-docstring
import filecmp
from pathlib import Path
from unittest import TestCase, mock

from gentoo_build_publisher import diff

BASE_DIR = Path(__file__).resolve().parent / "data"


class TestRemovePrefix(TestCase):
    """Tests for the removeprefix helper function"""

    def test_with_python38(self):
        with mock.patch.object(diff, "HAS_REMOVEPREFIX", new=True):
            string = "a.foo"
            prefix = "a."

            self.assertEqual(diff.removeprefix(string, prefix), "foo")

    def test_with_python38_no_prefix(self):
        with mock.patch.object(diff, "HAS_REMOVEPREFIX", new=True):
            string = "a.foo"
            prefix = "bar"

            self.assertEqual(diff.removeprefix(string, prefix), "a.foo")

    def test_without_python38(self):
        with mock.patch.object(diff, "HAS_REMOVEPREFIX", new=False):
            string = "a.foo"
            prefix = "a."

            self.assertEqual(diff.removeprefix(string, prefix), "foo")

    def test_without_python38_no_prefix(self):
        with mock.patch.object(diff, "HAS_REMOVEPREFIX", new=False):
            string = "a.foo"
            prefix = "bar"

            self.assertEqual(diff.removeprefix(string, prefix), "a.foo")


class TestRemoveSuffix(TestCase):
    """Tests for the removesuffix helper function"""

    def test_with_python38(self):
        with mock.patch.object(diff, "HAS_REMOVESUFFIX", new=True):
            string = "foo.a"
            suffix = ".a"

            self.assertEqual(diff.removesuffix(string, suffix), "foo")

    def test_with_python38_no_suffix(self):
        with mock.patch.object(diff, "HAS_REMOVESUFFIX", new=True):
            string = "foo.a"
            suffix = "bar"

            self.assertEqual(diff.removesuffix(string, suffix), "foo.a")

    def test_without_python38(self):
        with mock.patch.object(diff, "HAS_REMOVESUFFIX", new=False):
            string = "foo.a"
            suffix = ".a"

            self.assertEqual(diff.removesuffix(string, suffix), "foo")

    def test_without_python38_no_suffix(self):
        with mock.patch.object(diff, "HAS_REMOVESUFFIX", new=False):
            string = "foo.a"
            suffix = "bar"

            self.assertEqual(diff.removesuffix(string, suffix), "foo.a")


class TestPathToPackage(TestCase):
    """Tests for the path_to_pkg helper function"""

    def test_self(self):
        path = "/var/lib/gbp/binpkgs/babette.128/sys-apps/sandbox/sandbox-2.24-1.xpak"
        prefix = "/var/lib/gbp/binpkgs/babette.128"

        pkg = diff.path_to_pkg(prefix, path)

        self.assertEqual(pkg, "sys-apps/sandbox-2.24-1")


class TestChanges(TestCase):
    """Tests for the changes helper function"""

    def test(self):
        left = str(BASE_DIR / "binpkgs" / "babette.132")
        right = str(BASE_DIR / "binpkgs" / "babette.147")

        dircmp = filecmp.dircmp(left, right)
        gen = diff.changes(left, right, dircmp)

        items = set(gen)

        expected = {
            diff.Change(item="sys-apps/sandbox-2.24-1", status=diff.Status.REMOVED),
            diff.Change(item="sys-apps/portage-3.0.18-1", status=diff.Status.REMOVED),
            diff.Change(item="sys-apps/sandbox-2.23-1", status=diff.Status.ADDED),
            diff.Change(item="sys-apps/less-590-1", status=diff.Status.CHANGED),
            diff.Change(item="sys-apps/portage-3.0.18-2", status=diff.Status.ADDED),
        }
        self.assertEqual(items, expected)


class TestDirDiff(TestCase):
    """Tests for the dirdiff utility"""

    def test(self):
        left = str(BASE_DIR / "binpkgs" / "babette.132")
        right = str(BASE_DIR / "binpkgs" / "babette.147")

        gen = diff.dirdiff(left, right)

        items = set(gen)

        expected = {
            diff.Change(item="sys-apps/sandbox-2.24-1", status=diff.Status.REMOVED),
            diff.Change(item="sys-apps/portage-3.0.18-1", status=diff.Status.REMOVED),
            diff.Change(item="sys-apps/sandbox-2.23-1", status=diff.Status.ADDED),
            diff.Change(item="sys-apps/less-590-1", status=diff.Status.CHANGED),
            diff.Change(item="sys-apps/portage-3.0.18-2", status=diff.Status.ADDED),
        }
        self.assertEqual(items, expected)
