"""Unit tests for gbp views"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from . import TestCase


class IndexViewTestCase(TestCase):
    """Tests for the index view"""

    def test(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gentoo_build_publisher/index.html")
