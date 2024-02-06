"""Tests for the string module"""

# pylint: disable=missing-docstring
import io
import unittest

from gentoo_build_publisher import string

from . import parametrized


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


class GetBoolTestCase(unittest.TestCase):
    """Tests for get_bool()"""

    @parametrized([["0"], ["f"], ["false"], ["n"], ["no"], ["off"], [b"false"]])
    def test_false(self, value: str | bytes) -> None:
        self.assertIs(string.get_bool(value), False)

    @parametrized([["1"], ["t"], ["true"], ["y"], ["yes"], ["on"], [b"true"]])
    def test_true(self, value: str | bytes) -> None:
        self.assertIs(string.get_bool(value), True)

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            string.get_bool("bogus")

    def test_bool(self) -> None:
        self.assertIs(string.get_bool(True), True)
        self.assertIs(string.get_bool(False), False)
