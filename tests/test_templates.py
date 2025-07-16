"""Template tests"""

# pylint: disable=missing-docstring
from unittest import TestCase

from django.template import Context, Template


class BaseExtraHeadTests(TestCase):
    def test(self) -> None:
        template = Template(
            """
            {% extends "gentoo_build_publisher/base.html" %}
            {% block extra_head %}
            {{ block.super }}
            This is a test
            {% endblock %}
            """
        )
        content = template.render(Context({}))

        self.assertIn("This is a test", content)
