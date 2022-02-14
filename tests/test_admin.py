"""Tests for the admin interface"""
# pylint: disable=missing-class-docstring,missing-function-docstring

from unittest import mock

from django.contrib.auth import get_user_model

from gentoo_build_publisher.models import BuildNote, KeptBuild

from . import TestCase
from .factories import BuildModelFactory

User = get_user_model()


class BuildModelListViewFilterTestCase(TestCase):
    def setUp(self):
        super().setUp()

        BuildModelFactory.create()
        BuildModelFactory.create()
        kept = BuildModelFactory.create()
        KeptBuild.objects.create(build_model=kept)
        BuildNote.objects.create(build_model=kept, note="Test log")
        self.user = User.objects.create_superuser("root")

    def test_filter_on_keep_true(self):
        client = self.client

        client.force_login(self.user)
        response = client.get("/admin/gentoo_build_publisher/buildmodel/?keep=true")
        self.assertContains(response, "1 Build")

    def test_filter_on_keep_false(self):
        client = self.client

        client.force_login(self.user)
        response = client.get("/admin/gentoo_build_publisher/buildmodel/?keep=false")
        self.assertContains(response, "2 Builds")

    def test_filter_on_unfiltered(self):
        client = self.client

        client.force_login(self.user)
        response = client.get("/admin/gentoo_build_publisher/buildmodel/")
        self.assertContains(response, "3 Builds")


class BuildModelChangeViewTestCase(TestCase):
    def setUp(self):
        super().setUp()

        self.build_model = BuildModelFactory.create()
        self.user = User.objects.create_superuser("root")

    def test_keep_in_context(self):
        client = self.client
        build = self.build_model

        client.force_login(self.user)
        response = client.get(
            f"/admin/gentoo_build_publisher/buildmodel/{build.id}/change/"
        )
        self.assertEqual(response.context["keep"], False)

    def test_keep_action_unkept(self):
        client = self.client
        build = self.build_model

        client.force_login(self.user)
        url = f"/admin/gentoo_build_publisher/buildmodel/{build.id}/change/"
        post_data = {
            "_keep": "Keep",
            "buildnote-TOTAL_FORMS": "0",
            "buildnote-INITIAL_FORMS": "0",
        }
        client.post(url, post_data)

        self.assertTrue(KeptBuild.objects.filter(build_model=build).exists())

    def test_keep_action_kept(self):
        client = self.client
        build = self.build_model
        KeptBuild.objects.create(build_model=build)

        client.force_login(self.user)
        url = f"/admin/gentoo_build_publisher/buildmodel/{build.id}/change/"
        post_data = {
            "_keep": "Keep",
            "buildnote-TOTAL_FORMS": "0",
            "buildnote-INITIAL_FORMS": "0",
        }
        client.post(url, post_data)

        self.assertFalse(KeptBuild.objects.filter(build_model=build).exists())

    def test_publish_action(self):
        client = self.client
        build = BuildModelFactory.create()

        client.force_login(self.user)
        url = f"/admin/gentoo_build_publisher/buildmodel/{build.id}/change/"
        post_data = {
            "_publish": "Publish",
            "buildnote-TOTAL_FORMS": "0",
            "buildnote-INITIAL_FORMS": "0",
        }
        with mock.patch(
            "gentoo_build_publisher.managers.Build.publish"
        ) as mock_publish:
            client.post(url, post_data)

        self.assertTrue(mock_publish.called)
