"""Unit tests for gbp models"""
import datetime
import os
import tempfile
from unittest import mock

from django.test import TestCase

from gentoo_build_publisher.conf import settings
from gentoo_build_publisher.models import Build


class BuildTestCase(TestCase):
    """Unit tests for the Build model"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.work_dir = self.temp_dir.name
        patch = mock.patch.object(settings, "WORK_DIR", self.work_dir)
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
        mock_symlink.assert_any_call(source, f"{self.work_dir}/repos/babette")
        mock_symlink.assert_any_call(source, f"{self.work_dir}/binpkgs/babette")

    def test_downloads_archive_given_existing_symlinks(self):
        """Bug"""
        # Given the build
        build = self.build

        # given the existing symlinks
        os.makedirs(f"{self.work_dir}/repos")
        os.symlink(".", f"{self.work_dir}/repos/babette")
        os.makedirs(f"{self.work_dir}/binpkgs")
        os.symlink(".", f"{self.work_dir}/binpkgs/babette")

        # When we call its publish method
        with mock.patch.object(build, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.models.os.symlink") as mock_symlink:
                build.publish()

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates a symlink in the directory
        source = "babette.193"
        target = f"{self.work_dir}/repos/babette"
        mock_symlink.assert_any_call(source, target)
