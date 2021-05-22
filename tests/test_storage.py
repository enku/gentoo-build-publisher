"""Tests for the storage type"""
import os
from unittest import TestCase, mock

from gentoo_build_publisher import Build, Settings, Storage

from . import MockJenkins, TempHomeMixin

TEST_SETTINGS = Settings(
    STORAGE_PATH="/dev/null", JENKINS_BASE_URL="https://jenkins.invalid/"
)


class StorageInitTestCase(TempHomeMixin, TestCase):
    def test_creates_dir_if_not_exists(self):
        os.rmdir(self.tmpdir)

        Storage(self.tmpdir)
        self.assertIs(os.path.isdir(self.tmpdir), True)


class StorageReprTestCase(TempHomeMixin, TestCase):
    def test(self):
        storage = Storage(self.tmpdir)

        self.assertEqual(
            repr(storage), f"gentoo_build_publisher.Storage({repr(self.tmpdir)})"
        )


class StorageFromSettings(TempHomeMixin, TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test(self):
        """Should intantiate Storage from settings"""
        # Given the settings
        settings = TEST_SETTINGS.copy()
        settings.STORAGE_PATH = self.tmpdir

        # When we instantiate Storage.from_settings
        storage = Storage.from_settings(settings)

        # Then we get a Storage instance with attributes from settings
        self.assertIsInstance(storage, Storage)
        self.assertEqual(storage.path, self.tmpdir)


class StorageDownloadArtifactTestCase(TempHomeMixin, TestCase):
    """Tests for Storage.download_artifact"""

    def test_download_artifact_moves_repos_and_binpkgs(self):
        """Should download artifacts and move to repos/ and binpkgs/"""
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        build = Build(name="babette", number=19)
        storage.download_artifact(build, jenkins)

        self.assertIs(storage.get_path(build, "repos").is_dir(), True)
        self.assertIs(storage.get_path(build, "binpkgs").is_dir(), True)

    def test_download_artifact_creates_etc_portage_dir(self):
        """Should download artifacts and move to etc-portage/"""
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        build = Build(name="babette", number=19)
        storage.download_artifact(build, jenkins)

        self.assertIs(storage.get_path(build, "etc-portage").is_dir(), True)

    def test_download_artifact_creates_var_lib_portage_dir(self):
        """Should download artifacts and move to var-lib-portage/"""
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        build = Build(name="babette", number=19)
        storage.download_artifact(build, jenkins)

        self.assertIs(storage.get_path(build, "var-lib-portage").is_dir(), True)


class StoragePublishTestCase(TempHomeMixin, TestCase):
    """Tests for Storage.publish"""

    def test_publish_downloads_archive_if_repos_dir_does_not_exit(self):
        """Should download the archive if repos/<name>.<number> doesn't exist"""
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the build
        build = Build(name="babette", number=193)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        # When we call its publish method
        with mock.patch.object(storage, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.os.symlink") as mock_symlink:
                storage.publish(build, jenkins)

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates the symlinks
        source = "babette.193"
        mock_symlink.assert_any_call(source, f"{storage.path}/repos/babette")
        mock_symlink.assert_any_call(source, f"{storage.path}/binpkgs/babette")

    def test_downloads_archive_given_existing_symlinks(self):
        """Bug"""
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the build
        build = Build(name="babette", number=193)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        # given the existing symlinks
        for item in build.contents:
            os.makedirs(f"{storage.path}/{item}")
            os.symlink(".", f"{storage.path}/{item}/babette")

        # When we call its publish method
        with mock.patch.object(storage, "download_artifact") as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.os.symlink") as mock_symlink:
                storage.publish(build, jenkins)

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates a symlink in the directory
        target = f"{storage.path}/repos/{build.name}"
        mock_symlink.assert_any_call(str(build), target)


class StoragePublishedTestCase(TempHomeMixin, TestCase):
    """Tests for Storage.published"""

    def test_published_true(self):
        """.publshed should return True when published"""
        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

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
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        # Given the first build published
        build1 = Build(name="babette", number=192)
        storage.publish(build1, jenkins)

        # Given the second build published
        build2 = Build(name="babette", number=193)
        storage.publish(build2, jenkins)

        # Then published returns True on the second build
        self.assertTrue(storage.published(build2))

        # And False on the first build
        self.assertFalse(storage.published(build1))


class StorageDeleteBuildTestCase(TempHomeMixin, TestCase):
    """Tests for Storage.delete_build"""

    def test_deletes_expected_directories(self):
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        build = Build(name="babette", number=19)
        storage.download_artifact(build, jenkins)

        storage.delete_build(build)

        directories = [
            f"{storage.path}/binpkgs/{build}",
            f"{storage.path}/etc-portage/{build}",
            f"{storage.path}/repos/{build}",
            f"{storage.path}/var-lib-portage/{build}",
        ]
        for directory in directories:
            with self.subTest(directory=directory):
                self.assertIs(os.path.exists(directory), False)
