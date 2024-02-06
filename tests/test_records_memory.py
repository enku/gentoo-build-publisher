"""Tests for the memorydb module"""

# pylint: disable=missing-docstring
import unittest

from gentoo_build_publisher.records import BuildRecord, memory


class RecordKeyTestCase(unittest.TestCase):
    def test(self) -> None:
        self.assertEqual(memory.record_key(BuildRecord("babette", "16")), 16)
        self.assertEqual(memory.record_key(BuildRecord("babette", "xxx")), "xxx")
