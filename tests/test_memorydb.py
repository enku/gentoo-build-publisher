"""Tests for the memorydb module"""
# pylint: disable=missing-docstring
import unittest

from gentoo_build_publisher import memorydb
from gentoo_build_publisher.records import BuildRecord


class RecordKeyTestCase(unittest.TestCase):
    def test(self) -> None:
        self.assertEqual(memorydb.record_key(BuildRecord("babette", "16")), 16)
        self.assertEqual(memorydb.record_key(BuildRecord("babette", "xxx")), "xxx")
