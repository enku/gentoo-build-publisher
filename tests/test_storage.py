"""Tests for the storage type"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import os
from unittest import TestCase, mock

from gentoo_build_publisher import Build, Settings, StorageBuild

from . import MockJenkinsBuild, TempHomeMixin

TEST_SETTINGS = Settings(
    STORAGE_PATH="/dev/null", JENKINS_BASE_URL="https://jenkins.invalid/"
)


class StorageBuildInitTestCase(TempHomeMixin, TestCase):
    def test_creates_dir_if_not_exists(self):
        os.rmdir(self.tmpdir)
        build = Build(name="babette", number=19)

        StorageBuild(build, self.tmpdir)
        self.assertIs(os.path.isdir(self.tmpdir), True)


class StorageBuildReprTestCase(TempHomeMixin, TestCase):
    def test(self):
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)

        self.assertEqual(
            repr(storage_build),
            f"gentoo_build_publisher.StorageBuild({repr(self.tmpdir)})",
        )


class StorageBuildFromSettings(TempHomeMixin, TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test(self):
        """Should intantiate StorageBuild from settings"""
        # Given the build
        build = Build(name="babette", number=19)

        # Given the settings
        settings = TEST_SETTINGS.copy()
        settings.STORAGE_PATH = self.tmpdir

        # When we instantiate StorageBuild.from_settings
        storage_build = StorageBuild.from_settings(build, settings)

        # Then we get a StorageBuild instance with attributes from settings
        self.assertIsInstance(storage_build, StorageBuild)
        self.assertEqual(storage_build.path, self.tmpdir)


class StorageBuildDownloadArtifactTestCase(TempHomeMixin, TestCase):
    """Tests for StorageBuild.download_artifact"""

    def test_download_artifact_moves_repos_and_binpkgs(self):
        """Should download artifacts and move to repos/ and binpkgs/"""
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)
        storage_build.download_artifact(jenkins_build)

        self.assertIs(storage_build.get_path(Build.Content.REPOS).is_dir(), True)
        self.assertIs(storage_build.get_path(Build.Content.BINPKGS).is_dir(), True)

    def test_download_artifact_creates_etc_portage_dir(self):
        """Should download artifacts and move to etc-portage/"""
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)
        storage_build.download_artifact(jenkins_build)

        self.assertIs(storage_build.get_path(Build.Content.ETC_PORTAGE).is_dir(), True)

    def test_download_artifact_creates_var_lib_portage_dir(self):
        """Should download artifacts and move to var-lib-portage/"""
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)
        storage_build.download_artifact(jenkins_build)

        self.assertIs(
            storage_build.get_path(Build.Content.VAR_LIB_PORTAGE).is_dir(), True
        )


class StorageBuildPublishTestCase(TempHomeMixin, TestCase):
    """Tests for StorageBuild.publish"""

    def test_pull_downloads_archive_if_contents_dont_exist(self):
        # Given the build
        build = Build(name="babette", number=193)

        # Given the storage_build
        storage_build = StorageBuild(build, self.tmpdir)

        # Given the jenkins instance
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)

        # When we call its pull method
        with mock.patch.object(
            storage_build, "download_artifact"
        ) as mock_download_artifact:
            storage_build.pull(jenkins_build)

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

    def test_pull_does_not_download_archive_with_existing_content(self):
        # Given the build
        build = Build(name="babette", number=193)

        # Given the storage_build
        storage_build = StorageBuild(build, self.tmpdir)

        # Given the jenkins instance
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)

        # given the existing content
        for item in Build.Content:
            os.makedirs(storage_build.get_path(item))

        # When we call its publish method
        with mock.patch.object(
            storage_build, "download_artifact"
        ) as mock_download_artifact:
            storage_build.publish(jenkins_build)

        # Then it does not download the artifact
        mock_download_artifact.assert_not_called()

    def test_publish_downloads_archive_if_repos_dir_does_not_exit(self):
        """Should download the archive if repos/<name>.<number> doesn't exist"""
        # Given the build
        build = Build(name="babette", number=193)

        # Given the storage_build
        storage_build = StorageBuild(build, self.tmpdir)

        # Given the jenkins_build instance
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)

        # When we call its publish method
        with mock.patch.object(
            storage_build, "download_artifact"
        ) as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.os.symlink") as mock_symlink:
                storage_build.publish(jenkins_build)

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates the symlinks
        source = "babette.193"
        mock_symlink.assert_any_call(source, f"{storage_build.path}/repos/babette")
        mock_symlink.assert_any_call(source, f"{storage_build.path}/binpkgs/babette")

    def test_downloads_archive_given_existing_symlinks(self):
        """Bug"""
        # Given the build
        build = Build(name="babette", number=193)

        # Given the storage_build
        storage_build = StorageBuild(build, self.tmpdir)

        # Given the jenkins instance
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)

        # given the existing symlinks
        for item in build.Content:
            os.makedirs(f"{storage_build.path}/{item.value}")
            os.symlink(".", f"{storage_build.path}/{item.value}/babette")

        # When we call its publish method
        with mock.patch.object(
            storage_build, "download_artifact"
        ) as mock_download_artifact:
            with mock.patch("gentoo_build_publisher.os.symlink") as mock_symlink:
                storage_build.publish(jenkins_build)

        # Then it downloads the artifact
        mock_download_artifact.assert_called()

        # And creates a symlink in the directory
        target = f"{storage_build.path}/repos/{build.name}"
        mock_symlink.assert_any_call(str(build), target)


class StorageBuildPublishedTestCase(TempHomeMixin, TestCase):
    """Tests for StorageBuild.published"""

    def test_published_true(self):
        """.publshed should return True when published"""
        # Given the build
        build = Build(name="babette", number=193)

        # Given the storage_build
        storage_build = StorageBuild(build, self.tmpdir)

        # Given the jenkins instance
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)

        # When we publish the build
        storage_build.publish(jenkins_build)

        # And call published(build)
        published = storage_build.published()

        # Then it returns True
        self.assertTrue(published)

    def test_published_false(self):
        """.publshed should return False when not published"""
        # Given the unpublished build
        build = Build(name="babette", number=193)

        # Given the storage_build
        storage_build = StorageBuild(build, self.tmpdir)

        # When we acess the `published` attribute
        published = storage_build.published()

        # Then it returns False
        self.assertFalse(published)

    def test_other_published(self):
        # Given the first build published
        build1 = Build(name="babette", number=192)

        # Given the storage_build
        storage_build1 = StorageBuild(build1, self.tmpdir)

        # Given the jenkins instance
        jenkins_build = MockJenkinsBuild.from_settings(build1, TEST_SETTINGS)

        # When we publish the first build
        storage_build1.publish(jenkins_build)

        # Given the second build published
        build2 = Build(name="babette", number=193)
        storage_build2 = StorageBuild(build2, self.tmpdir)
        storage_build2.publish(jenkins_build)

        # Then published returns True on the second build
        self.assertTrue(storage_build2.published())

        # And False on the first build
        self.assertFalse(storage_build1.published())


class StorageBuildDeleteTestCase(TempHomeMixin, TestCase):
    """Tests for StorageBuild.delete"""

    def test_deletes_expected_directories(self):
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)
        storage_build.download_artifact(jenkins_build)

        storage_build.delete()

        directories = [
            f"{storage_build.path}/binpkgs/{build}",
            f"{storage_build.path}/etc-portage/{build}",
            f"{storage_build.path}/repos/{build}",
            f"{storage_build.path}/var-lib-portage/{build}",
        ]
        for directory in directories:
            with self.subTest(directory=directory):
                self.assertIs(os.path.exists(directory), False)
