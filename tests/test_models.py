"""Unit tests for gbp models"""
import datetime
import os
import tempfile
from unittest import mock

from django.test import TestCase

from gentoo_build_publisher.conf import settings
from gentoo_build_publisher.models import Build

from . import test_data


class BuildTestCase(TestCase):
    """Unit tests for the Build model"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home_dir = self.temp_dir.name
        patch = mock.patch.object(settings, "HOME_DIR", self.home_dir)
        patch.start()
        self.addCleanup(patch.stop)

        submitted = datetime.datetime(2021, 3, 23, 18, 39).replace(
            tzinfo=datetime.timezone.utc
        )
        self.build = Build.objects.create(
            build_name="babette", build_number=193, submitted=submitted
        )

    def test_publish_downloads_archive_if_repos_dir_does_not_exit(self):
        """Should download the archive if repos/<name>.<number> doesn't exist"""
        # Given the build
        build = self.build

        # When we call its publish method
        with mock.patch.object(build, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.models.os.symlink") as mock_symlink:
                build.publish()

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates the symlinks
        source = "babette.193"
        mock_symlink.assert_any_call(source, f"{self.home_dir}/repos/babette")
        mock_symlink.assert_any_call(source, f"{self.home_dir}/binpkgs/babette")

    def test_downloads_archive_given_existing_symlinks(self):
        """Bug"""
        # Given the build
        build = self.build

        # given the existing symlinks
        os.makedirs(f"{self.home_dir}/repos")
        os.symlink(".", f"{self.home_dir}/repos/babette")
        os.makedirs(f"{self.home_dir}/binpkgs")
        os.symlink(".", f"{self.home_dir}/binpkgs/babette")

        # When we call its publish method
        with mock.patch.object(build, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.models.os.symlink") as mock_symlink:
                build.publish()

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates a symlink in the directory
        source = "babette.193"
        target = f"{self.home_dir}/repos/babette"
        mock_symlink.assert_any_call(source, target)

    def test_download_artifact_moves_repos_and_binpks(self):
        """Should download artifacts and move to repos/ and binpkgs/"""
        # Given the build
        build = self.build

        # Given the (fake) artifact
        with mock.patch("gentoo_build_publisher.models.requests.get") as mock_get:
            response = mock_get.return_value
            response.iter_content.return_value = iter(
                [
                    test_data("build.tar.gz"),
                ]
            )
            # When we download the artifact
            build.download_artifact()

        # Then it creates the repos and binpks directories
        self.assertTrue(os.path.isdir(f"{self.home_dir}/repos/{build}"))
        self.assertTrue(os.path.isdir(f"{self.home_dir}/binpkgs/{build}"))

    def test_published_true(self):
        """.publshed should return True when published"""
        # Given the published build
        build = self.build

        with mock.patch("gentoo_build_publisher.models.requests.get") as mock_get:
            response = mock_get.return_value
            response.iter_content.return_value = iter(
                [
                    test_data("build.tar.gz"),
                ]
            )
            build.publish()

        # When we acess the `published` attribute
        published = build.published

        # Then it returns True
        self.assertTrue(published)

    def test_published_false(self):
        """.publshed should return False when not published"""
        # Given the unpublished build
        build = self.build

        # When we acess the `published` attribute
        published = build.published

        # Then it returns False
        self.assertFalse(published)
