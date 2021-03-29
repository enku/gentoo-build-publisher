"""Unit tests for gbp models"""
import os
from unittest import mock

from django.test import TestCase

from gentoo_build_publisher.types import Storage

from . import TempDirMixin
from .factories import BuildModelFactory


class BuildModelTestCase(TempDirMixin, TestCase):
    """Unit tests for the BuildModel"""

    def test_as_dict(self):
        """build.as_dict() should return the expected dict"""
        build_model = BuildModelFactory.create(storage=Storage(self.tmpdir))

        with mock.patch.dict(
            os.environ,
            {"BUILD_PUBLISHER_JENKINS_BASE_URL": "http://jenkins.invalid/job/Gentoo"},
        ):
            as_dict = build_model.as_dict()

        expected = {
            "name": "babette",
            "number": 193,
            "published": False,
            "url": "http://jenkins.invalid/job/Gentoo/job/babette/193/artifact/build.tar.gz",
        }
        self.assertEqual(as_dict, expected)
