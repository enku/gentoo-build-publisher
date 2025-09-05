"""Tests for the string module"""

# pylint: disable=missing-docstring
import io
import unittest

from unittest_fixtures import Fixtures, params

from gentoo_build_publisher.utils import string


class NameValueTestCase(unittest.TestCase):
    def test_splits_name_and_value_on_delim(self) -> None:
        self.assertEqual(string.namevalue("this:is a test", ":"), ("this", "is a test"))

    def test_strips_whitespace_around_name(self) -> None:
        self.assertEqual(
            string.namevalue(" this : is a test", ":"), ("this", "is a test")
        )

    def test_strips_whitespace_before_value(self) -> None:
        self.assertEqual(
            string.namevalue("this: is a test ", ":"), ("this", "is a test ")
        )

    def test_raises_error_when_delimiter_missing(self) -> None:
        with self.assertRaises(ValueError):
            string.namevalue("this is a test", ":")


class UntilBlankTestCase(unittest.TestCase):
    def test(self) -> None:
        mystr = """\
This
That

The
Other
"""
        gen = string.until_blank(io.StringIO(mystr))

        self.assertEqual(next(gen), "This")
        self.assertEqual(next(gen), "That")

        with self.assertRaises(StopIteration):
            next(gen)

    def test_with_initial_blank_lines(self) -> None:
        mystr = """\

This
That
"""
        gen = string.until_blank(io.StringIO(mystr))

        self.assertEqual(next(gen), "This")
        self.assertEqual(next(gen), "That")

    def test_empty_file(self) -> None:
        mystr = ""

        gen = string.until_blank(io.StringIO(mystr))

        with self.assertRaises(StopIteration):
            next(gen)

    def test_all_blanks(self) -> None:
        mystr = "\n\n\n  \n"

        gen = string.until_blank(io.StringIO(mystr))

        with self.assertRaises(StopIteration):
            next(gen)


class GetSectionsTestCase(unittest.TestCase):
    def test(self) -> None:
        mystr = """\
This
That


The
Other
"""
        gen = string.get_sections(io.StringIO(mystr))

        self.assertEqual(next(gen), ["This", "That"])
        self.assertEqual(next(gen), ["The", "Other"])

        with self.assertRaises(StopIteration):
            next(gen)


@params(
    string=[
        "acct-group/lpadmin-0-r3",
        "virtual/secret-service-0",
        "dev-libs/libatomic_ops-7.8.2",
        "dev-libs/libpcre-8.45-r4",
        "sys-libs/libblockdev-3.3.1",
    ]
)
@params(
    cpv=[
        ("acct-group", "lpadmin", "0-r3"),
        ("virtual", "secret-service", "0"),
        ("dev-libs", "libatomic_ops", "7.8.2"),
        ("dev-libs", "libpcre", "8.45-r4"),
        ("sys-libs", "libblockdev", "3.3.1"),
    ]
)
class SplitPkg(unittest.TestCase):
    def test(self, fixtures: Fixtures) -> None:
        self.assertEqual(string.split_pkg(fixtures.string), fixtures.cpv)


class SplitPkgValueError(unittest.TestCase):
    def test(self) -> None:
        with self.assertRaises(ValueError):
            string.split_pkg("foo-bar/baz-r1")
