"""Unit tests for gbp views"""
from unittest import mock

from django.test import RequestFactory, TestCase

from gentoo_build_publisher.models import Build
from gentoo_build_publisher.views import now, publish


class PublishViewTestCase(TestCase):
    """Tests for the publish view"""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory()

    def test_publish_new(self):
        """Should publish brand new builds"""
        request = self.request.post("/publish/")
        build_name = "babette"
        build_number = "193"

        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = publish(request, build_name, build_number)

        self.assertEqual(response.status_code, 200)
        build = Build.objects.get(build_name=build_name, build_number=build_number)
        mock_pb.delay.assert_called_once_with(build.pk)

    def test_publish_existing(self):
        """Should publish brand new builds"""
        request = self.request.post("/publish/")
        build_name = "babette"
        build_number = "193"
        build = Build.objects.create(
            build_name=build_name, build_number=build_number, submitted=now()
        )

        with mock.patch("gentoo_build_publisher.views.publish_build") as mock_pb:
            response = publish(request, build_name, build_number)

        self.assertEqual(response.status_code, 200)
        mock_pb.delay.assert_called_once_with(build.pk)
