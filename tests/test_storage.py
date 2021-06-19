"""Tests for the storage type"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import os
import shutil
import subprocess
import tarfile
from unittest import TestCase, mock

from gentoo_build_publisher.build import Build, Content
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import StorageBuild

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
            f"gentoo_build_publisher.storage.StorageBuild({repr(self.tmpdir)})",
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

    def test_extract_artifact_moves_repos_and_binpkgs(self):
        """Should extract artifacts and move to repos/ and binpkgs/"""
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)
        storage_build.extract_artifact(jenkins_build.download_artifact())

        self.assertIs(storage_build.get_path(Content.REPOS).is_dir(), True)
        self.assertIs(storage_build.get_path(Content.BINPKGS).is_dir(), True)

    def test_extract_artifact_creates_etc_portage_dir(self):
        """Should extract artifacts and move to etc-portage/"""
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)
        storage_build.extract_artifact(jenkins_build.download_artifact())

        self.assertIs(storage_build.get_path(Content.ETC_PORTAGE).is_dir(), True)

    def test_extract_artifact_creates_var_lib_portage_dir(self):
        """Should extract artifacts and move to var-lib-portage/"""
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)
        storage_build.extract_artifact(jenkins_build.download_artifact())

        self.assertIs(storage_build.get_path(Content.VAR_LIB_PORTAGE).is_dir(), True)


class StorageBuildPublishTestCase(TempHomeMixin, TestCase):
    """Tests for StorageBuild.publish"""

    def test_publish_raises_exception_repos_dir_does_not_exit(self):
        """Should raise an exception if the build has not been pulled"""
        # Given the build
        build = Build(name="babette", number=193)

        # Given the storage_build
        storage_build = StorageBuild(build, self.tmpdir)

        # Then an exception is raised
        with self.assertRaises(FileNotFoundError):
            # When we call publish
            storage_build.publish()


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
        storage_build.extract_artifact(jenkins_build.download_artifact())
        storage_build.publish()

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
        storage_build1.extract_artifact(jenkins_build.download_artifact())
        storage_build1.publish()

        # Given the second build published
        build2 = Build(name="babette", number=193)
        storage_build2 = StorageBuild(build2, self.tmpdir)
        storage_build2.extract_artifact(jenkins_build.download_artifact())
        storage_build2.publish()

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
        storage_build.extract_artifact(jenkins_build.download_artifact())

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


class StorageExtractArtifactTestCase(TempHomeMixin, TestCase):
    """Tests for StorageBuild.extract_artifact"""

    def test_does_not_extract_already_pulled_build(self):
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)

        storage_build.extract_artifact(jenkins_build.download_artifact())
        assert storage_build.pulled()

        # extract won't be able to extract this
        byte_stream_mock = iter([b""])

        try:
            storage_build.extract_artifact(byte_stream_mock)
        except tarfile.ReadError:
            self.fail("extract_artifact() should not have attempted to extract")

    def test_extracts_bytesteam_and_content(self):
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(build, TEST_SETTINGS)

        storage_build.extract_artifact(jenkins_build.download_artifact())

        self.assertIs(storage_build.pulled(), True)

    def test_uses_rsync_linkdest_if_previous_build_exists(self):
        previous_build = Build(name="babette", number=19)
        previous_storage_build = StorageBuild(previous_build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(previous_build, TEST_SETTINGS)
        previous_storage_build.extract_artifact(jenkins_build.download_artifact())
        shutil.rmtree(previous_storage_build.get_path(Content.REPOS))

        current_build = Build(name="babette", number=20)
        current_storage_build = StorageBuild(current_build, self.tmpdir)

        with mock.patch(
            "gentoo_build_publisher.storage.subprocess.run", wraps=subprocess.run
        ) as run_mock:
            current_storage_build.extract_artifact(
                jenkins_build.download_artifact(), previous_build=previous_storage_build
            )

        self.assertEqual(run_mock.call_count, len(Content) - 1)

        for item in Content:
            dst_path = current_storage_build.get_path(item)
            self.assertIs(dst_path.exists(), True)

            if item is Content.REPOS:
                continue

            link_dest_path = previous_storage_build.get_path(item)

            run_mock.assert_any_call(
                [
                    "rsync",
                    "--archive",
                    "--quiet",
                    f"--link-dest={link_dest_path}",
                    "--",
                    f"{self.tmpdir}/tmp/babette/20/{item.value}/",
                    f"{dst_path}/",
                ],
                check=True,
            )
