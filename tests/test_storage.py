"""Tests for the storage type"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
import json
import os
import tarfile
from unittest import mock

from gentoo_build_publisher.build import (
    Build,
    Content,
    GBPMetadata,
    Package,
    PackageMetadata,
)
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import StorageBuild, quick_check

from . import PACKAGE_INDEX, MockJenkinsBuild, TestCase
from .factories import BuildManFactory

TEST_SETTINGS = Settings(
    STORAGE_PATH="/dev/null", JENKINS_BASE_URL="https://jenkins.invalid/"
)


class StorageBuildInitTestCase(TestCase):
    def test_creates_dir_if_not_exists(self):
        os.rmdir(self.tmpdir)
        build = Build(name="babette", number=19)

        StorageBuild(build, self.tmpdir)
        self.assertIs(os.path.isdir(self.tmpdir), True)


class StorageBuildReprTestCase(TestCase):
    def test(self):
        build = Build(name="babette", number=19)
        storage_build = StorageBuild(build, self.tmpdir)

        self.assertEqual(
            repr(storage_build),
            f"gentoo_build_publisher.storage.StorageBuild({repr(self.tmpdir)})",
        )


class StorageBuildFromSettings(TestCase):
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


class StorageBuildDownloadArtifactTestCase(TestCase):
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


class StorageBuildPublishTestCase(TestCase):
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

    def test_raise_exception_when_symlink_target_exists_and_not_symlink(self):
        # Given the source and target which is not a symlink
        source = self.create_file("source")
        target = self.create_file("target")

        # Then an exception is raised
        with self.assertRaises(EnvironmentError) as cxt:
            # When we call synlink on source and target
            StorageBuild.symlink(source, target)

        exception = cxt.exception

        self.assertEqual(exception.args, (f"{target} exists but is not a symlink",))


class StorageBuildPublishedTestCase(TestCase):
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


class StorageBuildDeleteTestCase(TestCase):
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


class StorageExtractArtifactTestCase(TestCase):
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

    def test_uses_hard_link_if_previous_build_exists(self):
        previous_build = Build(name="babette", number=19)
        previous_storage_build = StorageBuild(previous_build, self.tmpdir)
        jenkins_build = MockJenkinsBuild.from_settings(previous_build, TEST_SETTINGS)
        previous_storage_build.extract_artifact(jenkins_build.download_artifact())

        current_build = Build(name="babette", number=20)
        current_storage_build = StorageBuild(current_build, self.tmpdir)

        current_storage_build.extract_artifact(
            jenkins_build.download_artifact(), previous_build=previous_storage_build
        )

        for item in Content:
            dst_path = current_storage_build.get_path(item)
            self.assertIs(dst_path.exists(), True)

        package_index = current_storage_build.get_path(Content.BINPKGS) / "Packages"
        self.assertEqual(package_index.stat().st_nlink, 2)


class StorageBuildGetPackagesTestCase(TestCase):
    """tests for the StorageBuild.get_packages() method"""

    def setUp(self):
        super().setUp()

        build = BuildManFactory.create()
        build.pull()
        self.storage_build = build.storage_build

    def test_should_return_list_of_packages_from_index(self):
        packages = self.storage_build.get_packages()

        self.assertEqual(len(packages), len(PACKAGE_INDEX))
        package = packages[0]
        self.assertEqual(package.cpv, "acct-group/sgx-0")
        self.assertEqual(package.repo, "gentoo")
        self.assertEqual(package.path, "acct-group/sgx/sgx-0-1.xpak")
        self.assertEqual(package.build_id, 1)
        self.assertEqual(package.size, 11362)
        self.assertEqual(package.build_time, 1622722899)

    def test_should_raise_lookuperror_when_index_file_missing(self):
        index_file = self.storage_build.get_path(Content.BINPKGS) / "Packages"
        index_file.unlink()

        with self.assertRaises(LookupError):
            self.storage_build.get_packages()


class StorageBuildGetMetadataTestCase(TestCase):
    """tests for the StorageBuild.get_metadata() method"""

    def setUp(self):
        super().setUp()

        build = BuildManFactory.create()
        build.pull()
        self.storage_build = build.storage_build

    def test_should_return_gbpmetadata_when_gbp_json_exists(self):
        metadata = self.storage_build.get_metadata()

        expected = GBPMetadata(
            build_duration=124,
            packages=PackageMetadata(
                total=4,
                size=889824,
                built=[
                    Package(
                        cpv="acct-group/sgx-0",
                        repo="gentoo",
                        path="acct-group/sgx/sgx-0-1.xpak",
                        build_id=1,
                        size=11362,
                        build_time=1622722899,
                    ),
                    Package(
                        cpv="app-admin/perl-cleaner-2.30",
                        repo="gentoo",
                        path="app-admin/perl-cleaner/perl-cleaner-2.30-1.xpak",
                        build_id=1,
                        size=17686,
                        build_time=1621623613,
                    ),
                    Package(
                        cpv="app-crypt/gpgme-1.14.0",
                        repo="gentoo",
                        path="app-crypt/gpgme/gpgme-1.14.0-1.xpak",
                        build_id=1,
                        size=640649,
                        build_time=1622585986,
                    ),
                ],
            ),
        )
        self.assertEqual(metadata, expected)

    def test_should_raise_lookuperror_when_file_does_not_exist(self):
        path = self.storage_build.get_path(Content.BINPKGS) / "gbp.json"
        path.unlink()

        with self.assertRaises(LookupError) as context:
            self.storage_build.get_metadata()

        exception = context.exception
        self.assertEqual(exception.args, ("gbp.json does not exist",))


class StorageBuildSetMetadataTestCase(TestCase):
    """tests for the StorageBuild.set_metadata() method"""

    def setUp(self):
        super().setUp()
        build = BuildManFactory.create()
        build.pull()
        self.storage_build = build.storage_build
        self.path = self.storage_build.get_path(Content.BINPKGS) / "gbp.json"

        if self.path.exists():
            self.path.unlink()

    def test(self):
        package_metadata = PackageMetadata(
            total=666,
            size=666,
            built=[
                Package(
                    "sys-foo/bar-1.0",
                    repo="marduk",
                    path="",
                    build_id=1,
                    size=666,
                    build_time=0,
                )
            ],
        )
        gbp_metadata = GBPMetadata(build_duration=666, packages=package_metadata)
        self.storage_build.set_metadata(gbp_metadata)

        with self.path.open("r") as json_file:
            result = json.load(json_file)

        expected = {
            "build_duration": 666,
            "packages": {
                "built": [
                    {
                        "build_id": 1,
                        "build_time": 0,
                        "cpv": "sys-foo/bar-1.0",
                        "path": "",
                        "repo": "marduk",
                        "size": 666,
                    }
                ],
                "size": 666,
                "total": 666,
            },
        }
        self.assertEqual(result, expected)


class QuickCheckTestCase(TestCase):
    """Tests for the quick_check() helper method"""

    def test(self):
        timestamp = datetime.datetime(2021, 10, 30, 7, 10, 39)
        file1 = self.create_file("foo", b"test", timestamp)
        file2 = self.create_file("bar", b"xxxx", timestamp)

        result = quick_check(file1, file2)

        self.assertIs(result, True)

    def test_should_return_false_when_file_does_not_exist(self):
        timestamp = datetime.datetime(2021, 10, 30, 7, 10, 39)
        file1 = self.create_file("foo", b"test", timestamp)
        file2 = self.tmpdir / "bogus"

        result = quick_check(file1, file2)

        self.assertIs(result, False)

    def test_should_return_false_when_mtimes_differ(self):
        timestamp1 = datetime.datetime(2021, 10, 30, 7, 10, 39)
        timestamp2 = datetime.datetime(2021, 10, 30, 7, 10, 40)
        file1 = self.create_file("foo", b"test", timestamp1)
        file2 = self.create_file("bar", b"test", timestamp2)

        result = quick_check(file1, file2)

        self.assertIs(result, False)

    def test_should_return_false_when_sizes_differ(self):
        timestamp = datetime.datetime(2021, 10, 30, 7, 10, 39)
        file1 = self.create_file("foo", b"test", timestamp)
        file2 = self.create_file("bar", b"tst", timestamp)

        result = quick_check(file1, file2)

        self.assertIs(result, False)
