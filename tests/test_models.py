"""Unit tests for gbp models"""
import os
from unittest import mock

from django.test import TestCase

from . import mock_get_artifact, mock_home_dir
from .factories import BuildFactory


class BuildTestCase(TestCase):
    """Unit tests for the Build model"""

    def test_publish_downloads_archive_if_repos_dir_does_not_exit(self):
        """Should download the archive if repos/<name>.<number> doesn't exist"""
        # Given the build
        build = BuildFactory.create()

        # When we call its publish method
        with mock.patch.object(build, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.models.os.symlink") as mock_symlink:
                with mock_home_dir() as home_dir:
                    build.publish()

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates the symlinks
        source = "babette.193"
        mock_symlink.assert_any_call(source, f"{home_dir}/repos/babette")
        mock_symlink.assert_any_call(source, f"{home_dir}/binpkgs/babette")

    def test_downloads_archive_given_existing_symlinks(self):
        """Bug"""
        # Given the build
        build = BuildFactory.create()

        # given the existing symlinks
        with mock_home_dir() as home_dir:
            os.makedirs(f"{home_dir}/repos")
            os.symlink(".", f"{home_dir}/repos/babette")
            os.makedirs(f"{home_dir}/binpkgs")
            os.symlink(".", f"{home_dir}/binpkgs/babette")

            # When we call its publish method
            with mock.patch.object(
                build, "download_artifact"
            ) as mock_download_artifact:
                with mock.patch(
                    "gentoo_build_publisher.models.os.symlink"
                ) as mock_symlink:
                    build.publish()

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates a symlink in the directory
        source = str(build)
        target = f"{home_dir}/repos/{build.build_name}"
        mock_symlink.assert_any_call(source, target)

    def test_download_artifact_moves_repos_and_binpks(self):
        """Should download artifacts and move to repos/ and binpkgs/"""
        # Given the build
        build = BuildFactory.create()

        # Given the (fake) artifact
        with mock_get_artifact():
            # When we download the artifact
            with mock_home_dir() as home_dir:
                build.download_artifact()

                # Then it creates the repos and binpks directories
                self.assertTrue(os.path.isdir(f"{home_dir}/repos/{build}"))
                self.assertTrue(os.path.isdir(f"{home_dir}/binpkgs/{build}"))

    def test_published_true(self):
        """.publshed should return True when published"""
        # Given the published build
        build = BuildFactory.create()

        with mock_get_artifact():
            with mock_home_dir():
                build.publish()

                # When we acess the `published` attribute
                published = build.published

                # Then it returns True
                self.assertTrue(published)

    def test_published_false(self):
        """.publshed should return False when not published"""
        # Given the unpublished build
        build = BuildFactory.create()

        # When we acess the `published` attribute
        published = build.published

        # Then it returns False
        self.assertFalse(published)

    def test_as_dict(self):
        """build.as_dict() should return the expected dict"""
        build = BuildFactory.create()

        expected = {
            "buildName": "babette",
            "buildNumber": 193,
            "published": False,
            "url": "http://jenkins.invalid/job/Gentoo/job/babette/193/artifact/build.tar.gz",
        }
        self.assertEqual(build.as_dict(), expected)
