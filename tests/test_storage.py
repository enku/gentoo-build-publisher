"""Tests for the storage type"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
import json
import os
import tarfile
from unittest import mock

from gentoo_build_publisher import utils
from gentoo_build_publisher.build import (
    BuildID,
    Content,
    GBPMetadata,
    Package,
    PackageMetadata,
)
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage, quick_check

from . import PACKAGE_INDEX, MockJenkins, TestCase
from .factories import BuildIDFactory, BuildPublisherFactory

TEST_SETTINGS = Settings(
    STORAGE_PATH="/dev/null", JENKINS_BASE_URL="https://jenkins.invalid/"
)


class StorageInitTestCase(TestCase):
    def test_creates_dir_if_not_exists(self):
        os.rmdir(self.tmpdir)

        Storage(self.tmpdir)
        self.assertIs(os.path.isdir(self.tmpdir), True)


class StorageReprTestCase(TestCase):
    def test(self):
        storage = Storage(self.tmpdir)

        self.assertEqual(
            repr(storage),
            f"gentoo_build_publisher.storage.Storage({repr(self.tmpdir)})",
        )


class StorageFromSettings(TestCase):
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


class StorageDownloadArtifactTestCase(TestCase):
    """Tests for Storage.download_artifact"""

    def test_extract_artifact_moves_repos_and_binpkgs(self):
        """Should extract artifacts and move to repos/ and binpkgs/"""
        build_id = BuildID("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        storage.extract_artifact(build_id, jenkins.download_artifact(build_id))

        self.assertIs(storage.get_path(build_id, Content.REPOS).is_dir(), True)
        self.assertIs(storage.get_path(build_id, Content.BINPKGS).is_dir(), True)

    def test_extract_artifact_creates_etc_portage_dir(self):
        """Should extract artifacts and move to etc-portage/"""
        build_id = BuildID("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        storage.extract_artifact(build_id, jenkins.download_artifact(build_id))

        self.assertIs(storage.get_path(build_id, Content.ETC_PORTAGE).is_dir(), True)

    def test_extract_artifact_creates_var_lib_portage_dir(self):
        """Should extract artifacts and move to var-lib-portage/"""
        build_id = BuildID("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        storage.extract_artifact(build_id, jenkins.download_artifact(build_id))

        self.assertIs(
            storage.get_path(build_id, Content.VAR_LIB_PORTAGE).is_dir(), True
        )

    def test_extract_artifact_should_remove_dst_if_it_already_exists(self):
        build_publisher = BuildPublisherFactory()

        # Given the extractable build
        build_id = BuildIDFactory()

        # When when one of the target paths already exist
        path = build_publisher.storage.get_path(build_id, Content.BINPKGS)
        path.mkdir(parents=True)
        orphan = path / "this should not be here"
        orphan.touch()

        # And we extract the build
        build_publisher.storage.extract_artifact(
            build_id, build_publisher.jenkins.download_artifact(build_id)
        )

        # Then the orpaned path is removed
        self.assertIs(path.exists(), True)
        self.assertIs(orphan.exists(), False)


class StoragePublishTestCase(TestCase):
    """Tests for Storage.publish"""

    def test_publish_raises_exception_repos_dir_does_not_exist(self):
        """Should raise an exception if the build has not been pulled"""
        # Given the build
        build_id = BuildID("babette.193")

        # Given the storage
        storage = Storage(self.tmpdir)

        # Then an exception is raised
        with self.assertRaises(FileNotFoundError):
            # When we call publish
            storage.publish(build_id)

    def test_raise_exception_when_symlink_target_exists_and_not_symlink(self):
        # Given the source and target which is not a symlink
        source = self.create_file("source")
        target = self.create_file("target")

        # Then an exception is raised
        with self.assertRaises(EnvironmentError) as cxt:
            # When we call synlink on source and target
            Storage.symlink(str(source), str(target))

        exception = cxt.exception

        self.assertEqual(exception.args, (f"{target} exists but is not a symlink",))


class StoragePublishedTestCase(TestCase):
    """Tests for Storage.published"""

    def test_published_true(self):
        """.publshed should return True when published"""
        # Given the build
        build_id = BuildID("babette.193")

        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        # When we publish the build
        storage.extract_artifact(build_id, jenkins.download_artifact(build_id))
        storage.publish(build_id)

        # And call published(build)
        published = storage.published(build_id)

        # Then it returns True
        self.assertTrue(published)

    def test_published_false(self):
        """.publshed should return False when not published"""
        # Given the unpublished build
        build_id = BuildID("babette.193")

        # Given the storage
        storage = Storage(self.tmpdir)

        # When we acess the `published` attribute
        published = storage.published(build_id)

        # Then it returns False
        self.assertFalse(published)

    def test_other_published(self):
        # Given the first build published
        build1_id = BuildID("babette.192")

        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        # When we publish the first build
        storage.extract_artifact(build1_id, jenkins.download_artifact(build1_id))
        storage.publish(build1_id)

        # Given the second build published
        build2_id = BuildID("babette.193")
        storage.extract_artifact(build2_id, jenkins.download_artifact(build2_id))
        storage.publish(build2_id)

        # Then published returns True on the second build
        self.assertTrue(storage.published(build2_id))

        # And False on the first build
        self.assertFalse(storage.published(build1_id))


class StorageDeleteTestCase(TestCase):
    """Tests for Storage.delete"""

    def test_deletes_expected_directories(self):
        build = BuildID("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        storage.extract_artifact(build, jenkins.download_artifact(build))

        storage.delete(build)

        directories = [
            f"{storage.path}/binpkgs/{build}",
            f"{storage.path}/etc-portage/{build}",
            f"{storage.path}/repos/{build}",
            f"{storage.path}/var-lib-portage/{build}",
        ]
        for directory in directories:
            with self.subTest(directory=directory):
                self.assertIs(os.path.exists(directory), False)


class StorageExtractArtifactTestCase(TestCase):
    """Tests for Storage.extract_artifact"""

    def test_does_not_extract_already_pulled_build(self):
        build_id = BuildID("build.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        storage.extract_artifact(build_id, jenkins.download_artifact(build_id))
        assert storage.pulled(build_id)

        # extract won't be able to extract this
        byte_stream_mock = iter([b""])

        try:
            storage.extract_artifact(build_id, byte_stream_mock)
        except tarfile.ReadError:
            self.fail("extract_artifact() should not have attempted to extract")

    def test_extracts_bytesteam_and_content(self):
        build_id = BuildID("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        storage.extract_artifact(build_id, jenkins.download_artifact(build_id))

        self.assertIs(storage.pulled(build_id), True)

    def test_uses_hard_link_if_previous_build_exists(self):
        previous_build_id = BuildID("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        storage.extract_artifact(
            previous_build_id, jenkins.download_artifact(previous_build_id)
        )

        current_build_id = BuildID("babette.20")

        storage.extract_artifact(
            current_build_id,
            jenkins.download_artifact(current_build_id),
            previous_build=previous_build_id,
        )

        for item in Content:
            dst_path = storage.get_path(current_build_id, item)
            self.assertIs(dst_path.exists(), True)

        package_index = storage.get_path(current_build_id, Content.BINPKGS) / "Packages"
        self.assertEqual(package_index.stat().st_nlink, 2)


class StorageGetPackagesTestCase(TestCase):
    """tests for the Storage.get_packages() method"""

    def setUp(self):
        super().setUp()

        self.build_id = BuildIDFactory()
        build_publisher = BuildPublisherFactory()
        build_publisher.pull(self.build_id)
        self.storage = build_publisher.storage

    def test_should_return_list_of_packages_from_index(self):
        packages = self.storage.get_packages(self.build_id)

        self.assertEqual(len(packages), len(PACKAGE_INDEX))
        package = packages[0]
        self.assertEqual(package.cpv, "acct-group/sgx-0")
        self.assertEqual(package.repo, "gentoo")
        self.assertEqual(package.path, "acct-group/sgx/sgx-0-1.xpak")
        self.assertEqual(package.build_id, 1)
        self.assertEqual(package.size, 11362)
        self.assertEqual(package.build_time, 1622722899)

    def test_should_raise_lookuperror_when_index_file_missing(self):
        index_file = self.storage.get_path(self.build_id, Content.BINPKGS) / "Packages"
        index_file.unlink()

        with self.assertRaises(LookupError):
            self.storage.get_packages(self.build_id)


class StorageGetMetadataTestCase(TestCase):
    """tests for the Storage.get_metadata() method"""

    def setUp(self):
        super().setUp()

        self.build_id = BuildIDFactory()
        self.build_publisher = BuildPublisherFactory()
        self.build_publisher.pull(self.build_id)
        self.storage = self.build_publisher.storage

    def test_should_return_gbpmetadata_when_gbp_json_exists(self):
        metadata = self.storage.get_metadata(self.build_id)

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
        path = self.storage.get_path(self.build_id, Content.BINPKGS) / "gbp.json"
        path.unlink()

        with self.assertRaises(LookupError) as context:
            self.storage.get_metadata(self.build_id)

        exception = context.exception
        self.assertEqual(exception.args, ("gbp.json does not exist",))


class StorageSetMetadataTestCase(TestCase):
    """tests for the Storage.set_metadata() method"""

    def setUp(self):
        super().setUp()
        self.build_id = BuildIDFactory()
        build_publisher = BuildPublisherFactory()
        build_publisher.pull(self.build_id)
        self.storage = build_publisher.storage
        self.path = self.storage.get_path(self.build_id, Content.BINPKGS) / "gbp.json"

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
        self.storage.set_metadata(self.build_id, gbp_metadata)

        with self.path.open("r") as json_file:
            result = json.load(json_file)

        expected = {
            "build_duration": 666,
            "gbp_hostname": utils.get_hostname(),
            "gbp_version": utils.get_version(),
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
