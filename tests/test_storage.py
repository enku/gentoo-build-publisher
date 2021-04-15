"""Tests for the storage type"""
import os
from unittest import TestCase, mock

from gentoo_build_publisher.types import Build, Jenkins, Settings, Storage

from . import MockJenkins, TempHomeMixin


class StorageInitTestCase(TempHomeMixin, TestCase):
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

    def test_creates_etc_portage_dir_if_not_exists(self):
        Storage(self.tmpdir)
        etc_portage_dir = f"{self.tmpdir}/etc-portage"

        self.assertIs(os.path.isdir(etc_portage_dir), True)

    def test_creates_var_lib_portage_dir_if_not_exists(self):
        Storage(self.tmpdir)
        var_lib_portage_dir = f"{self.tmpdir}/var-lib-portage"

        self.assertIs(os.path.isdir(var_lib_portage_dir), True)

    def test_has_etc_portage_attribute(self):
        storage = Storage(self.tmpdir)
        etc_portage_dir = f"{self.tmpdir}/etc-portage"

        self.assertEqual(storage.etc_portage, etc_portage_dir)

    def test_has_binpkgs_attribute(self):
        storage = Storage(self.tmpdir)
        binpkgs_dir = f"{self.tmpdir}/binpkgs"

        self.assertEqual(storage.binpkgs, binpkgs_dir)

    def test_has_repos_attribute(self):
        storage = Storage(self.tmpdir)
        repos_dir = f"{self.tmpdir}/repos"

        self.assertEqual(storage.repos, repos_dir)


class StorageFromSettings(TempHomeMixin, TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test(self):
        """Should intantiate Storage from settings"""
        # Given the settings
        settings = Settings(HOME_DIR=self.tmpdir)

        # When we instantiate Storage.from_settings
        storage = Storage.from_settings(settings)

        # Then we get a Storage instance with attributes from settings
        self.assertIsInstance(storage, Storage)
        self.assertEqual(storage.dirname, self.tmpdir)


class StorageDownloadArtifactTestCase(TempHomeMixin, TestCase):
    """Tests for Storage.download_artifact"""

    def test_download_artifact_moves_repos_and_binpkgs(self):
        """Should download artifacts and move to repos/ and binpkgs/"""
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(Settings())
        build = Build(name="babette", number=19)
        storage.download_artifact(build, jenkins)

        self.assertIs(os.path.isdir(storage.build_repos(build)), True)
        self.assertIs(os.path.isdir(storage.build_binpkgs(build)), True)

    def test_download_artifact_creates_etc_portage_dir(self):
        """Should download artifacts and move to etc-portage/"""
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(Settings())
        build = Build(name="babette", number=19)
        storage.download_artifact(build, jenkins)

        self.assertIs(os.path.isdir(storage.build_etc_portage(build)), True)

    def test_download_artifact_creates_var_lib_portage_dir(self):
        """Should download artifacts and move to var-lib-portage/"""
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(Settings())
        build = Build(name="babette", number=19)
        storage.download_artifact(build, jenkins)

        self.assertIs(os.path.isdir(storage.build_var_lib_portage(build)), True)


class StoragePublishTestCase(TempHomeMixin, TestCase):
    """Tests for Storage.publish"""

    def test_publish_downloads_archive_if_repos_dir_does_not_exit(self):
        """Should download the archive if repos/<name>.<number> doesn't exist"""
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the build
        build = Build(name="babette", number=193)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(Settings())

        # When we call its publish method
        with mock.patch.object(storage, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.types.os.symlink") as mock_symlink:
                storage.publish(build, jenkins)

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

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(Settings())

        # given the existing symlinks
        os.symlink(".", f"{storage.dirname}/repos/babette")
        os.symlink(".", f"{storage.dirname}/binpkgs/babette")

        # When we call its publish method
        with mock.patch.object(storage, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.types.os.symlink") as mock_symlink:
                storage.publish(build, jenkins)

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates a symlink in the directory
        target = f"{storage.dirname}/repos/{build.name}"
        mock_symlink.assert_any_call(str(build), target)


class StoragePublishedTestCase(TempHomeMixin, TestCase):
    """Tests for Storage.published"""

    def test_published_true(self):
        """.publshed should return True when published"""
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(Settings())

        # Given the published build
        build = Build(name="babette", number=193)
        storage.publish(build, jenkins)

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

    def test_other_published(self):
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(Settings())

        # Given the first build published
        build1 = Build(name="babette", number=193)
        storage.publish(build1, jenkins)

        # Given the second build published
        build2 = Build(name="babette", number=192)
        storage.publish(build2, jenkins)

        # Then published returns True on the second build
        self.assertTrue(storage.published(build2))

        # And False on the first build
        self.assertFalse(storage.published(build1))
