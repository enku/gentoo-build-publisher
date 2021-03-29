"""Tests for the storage type"""
import os
from unittest import TestCase, mock

from gentoo_build_publisher.conf import GBPSettings
from gentoo_build_publisher.types import Build, Storage

from . import TempDirMixin, mock_get_artifact


class StorageInitTestCase(TempDirMixin, TestCase):
    def test_creates_dir_if_not_exists(self):
        os.rmdir(self.tmpdir)

        Storage(self.tmpdir)
        self.assertIs(os.path.isdir(self.tmpdir), True)

    def test_creates_binpkgs_dir_if_not_exists(self):
        Storage(self.tmpdir)
        binpkgs_dir = f"{self.tmpdir}/binpkgs"

        self.assertIs(os.path.isdir(binpkgs_dir), True)

    def test_creates_repos_dir_if_not_exists(self):
        Storage(self.tmpdir)
        repos_dir = f"{self.tmpdir}/repos"

        self.assertIs(os.path.isdir(repos_dir), True)

    def test_has_binpkgs_attribute(self):
        storage = Storage(self.tmpdir)
        binpkgs_dir = f"{self.tmpdir}/binpkgs"

        self.assertEqual(storage.binpkgs, binpkgs_dir)

    def test_has_repos_attribute(self):
        storage = Storage(self.tmpdir)
        repos_dir = f"{self.tmpdir}/repos"

        self.assertEqual(storage.repos, repos_dir)


class StorageFromSettings(TempDirMixin, TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test(self):
        """Should intantiate Storage from settings"""
        # Given the settings
        values = {"HOME_DIR": self.tmpdir}
        my_settings = GBPSettings("BUILD_PUBLISHER_", values)

        # When we instantiate Storage.from_settings
        storage = Storage.from_settings(my_settings)

        # Then we get a Storage instance with attributes from my_settings
        self.assertIsInstance(storage, Storage)
        self.assertEqual(storage.dirname, self.tmpdir)


class StorageDownloadArtifactTestCase(TempDirMixin, TestCase):
    """Tests for Storage.download_artifact"""

    @mock_get_artifact
    def test_download_artifact_moves_repos_and_binpkgs(self):
        """Should download artifacts and move to repos/ and binpkgs/"""
        storage = Storage(self.tmpdir)
        build = Build(name="babette", number=19)
        storage.download_artifact(build)

        self.assertIs(os.path.isdir(storage.build_repos(build)), True)
        self.assertIs(os.path.isdir(storage.build_binpkgs(build)), True)


class StoragePublishTestCase(TempDirMixin, TestCase):
    """Tests for Storage.publish"""

    def test_publish_downloads_archive_if_repos_dir_does_not_exit(self):
        """Should download the archive if repos/<name>.<number> doesn't exist"""
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the build
        build = Build(name="babette", number=193)

        # When we call its publish method
        with mock.patch.object(storage, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.types.os.symlink") as mock_symlink:
                storage.publish(build)

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates the symlinks
        source = "babette.193"
        mock_symlink.assert_any_call(source, f"{storage.dirname}/repos/babette")
        mock_symlink.assert_any_call(source, f"{storage.dirname}/binpkgs/babette")

    def test_downloads_archive_given_existing_symlinks(self):
        """Bug"""
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the build
        build = Build(name="babette", number=193)

        # given the existing symlinks
        os.symlink(".", f"{storage.dirname}/repos/babette")
        os.symlink(".", f"{storage.dirname}/binpkgs/babette")

        # When we call its publish method
        with mock.patch.object(storage, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.types.os.symlink") as mock_symlink:
                storage.publish(build)

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates a symlink in the directory
        target = f"{storage.dirname}/repos/{build.name}"
        mock_symlink.assert_any_call(str(build), target)


class StoragePublishedTestCase(TempDirMixin, TestCase):
    """Tests for Storage.published"""

    @mock_get_artifact
    def test_published_true(self):
        """.publshed should return True when published"""
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the published build
        build = Build(name="babette", number=193)
        storage.publish(build)

        # When we call published(build)
        published = storage.published(build)

        # Then it returns True
        self.assertTrue(published)

    def test_published_false(self):
        """.publshed should return False when not published"""
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the unpublished build
        build = Build(name="babette", number=193)

        # When we acess the `published` attribute
        published = storage.published(build)

        # Then it returns False
        self.assertFalse(published)
