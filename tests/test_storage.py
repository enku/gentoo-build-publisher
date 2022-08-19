"""Tests for the storage type"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
import json
import os
import shutil
import tarfile
from unittest import mock

from gentoo_build_publisher import utils
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage, quick_check
from gentoo_build_publisher.types import (
    Build,
    Content,
    GBPMetadata,
    Package,
    PackageMetadata,
)

from . import PACKAGE_INDEX, MockJenkins, TestCase
from .factories import BuildFactory

TEST_SETTINGS = Settings(
    STORAGE_PATH="/dev/null", JENKINS_BASE_URL="https://jenkins.invalid/"
)


class StorageInitTestCase(TestCase):
    def test_creates_dir_if_not_exists(self):
        shutil.rmtree(self.tmpdir)

        Storage(self.tmpdir)
        self.assertIs(os.path.isdir(self.tmpdir), True)


class StorageReprTestCase(TestCase):
    def test(self):
        storage = Storage(self.tmpdir)

        self.assertEqual(repr(storage), f"Storage({repr(self.tmpdir)})")


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
        self.assertEqual(storage.root, self.tmpdir)


class StorageDownloadArtifactTestCase(TestCase):
    """Tests for Storage.download_artifact"""

    def test_extract_artifact_moves_repos_and_binpkgs(self):
        """Should extract artifacts and move to repos/ and binpkgs/"""
        build = Build("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        storage.extract_artifact(build, jenkins.download_artifact(build))

        self.assertIs(storage.get_path(build, Content.REPOS).is_dir(), True)
        self.assertIs(storage.get_path(build, Content.BINPKGS).is_dir(), True)

    def test_extract_artifact_creates_etc_portage_dir(self):
        """Should extract artifacts and move to etc-portage/"""
        build = Build("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        storage.extract_artifact(build, jenkins.download_artifact(build))

        self.assertIs(storage.get_path(build, Content.ETC_PORTAGE).is_dir(), True)

    def test_extract_artifact_creates_var_lib_portage_dir(self):
        """Should extract artifacts and move to var-lib-portage/"""
        build = Build("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        storage.extract_artifact(build, jenkins.download_artifact(build))

        self.assertIs(storage.get_path(build, Content.VAR_LIB_PORTAGE).is_dir(), True)

    def test_extract_artifact_should_remove_dst_if_it_already_exists(self):
        # Given the extractable build
        build = BuildFactory()

        # When when one of the target paths already exist
        path = self.publisher.storage.get_path(build, Content.BINPKGS)
        path.mkdir(parents=True)
        orphan = path / "this should not be here"
        orphan.touch()

        # And we extract the build
        self.publisher.storage.extract_artifact(
            build, self.publisher.jenkins.download_artifact(build)
        )

        # Then the orpaned path is removed
        self.assertIs(path.exists(), True)
        self.assertIs(orphan.exists(), False)


class StoragePublishTestCase(TestCase):
    """Tests for Storage.publish"""

    def test_publish_raises_exception_repos_dir_does_not_exist(self):
        """Should raise an exception if the build has not been pulled"""
        # Given the build
        build = Build("babette.193")

        # Given the storage
        storage = Storage(self.tmpdir)

        # Then an exception is raised
        with self.assertRaises(FileNotFoundError):
            # When we call publish
            storage.publish(build)

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
        build = Build("babette.193")

        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        # When we publish the build
        storage.extract_artifact(build, jenkins.download_artifact(build))
        storage.publish(build)

        # And call published(build)
        published = storage.published(build)

        # Then it returns True
        self.assertTrue(published)

    def test_published_false(self):
        """.publshed should return False when not published"""
        # Given the unpublished build
        build = Build("babette.193")

        # Given the storage
        storage = Storage(self.tmpdir)

        # When we acess the `published` attribute
        published = storage.published(build)

        # Then it returns False
        self.assertFalse(published)

    def test_other_published(self):
        # Given the first build published
        build1_id = Build("babette.192")

        # Given the storage
        storage = Storage(self.tmpdir)

        # Given the jenkins instance
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        # When we publish the first build
        storage.extract_artifact(build1_id, jenkins.download_artifact(build1_id))
        storage.publish(build1_id)

        # Given the second build published
        build2_id = Build("babette.193")
        storage.extract_artifact(build2_id, jenkins.download_artifact(build2_id))
        storage.publish(build2_id)

        # Then published returns True on the second build
        self.assertTrue(storage.published(build2_id))

        # And False on the first build
        self.assertFalse(storage.published(build1_id))


class StorageDeleteTestCase(TestCase):
    """Tests for Storage.delete"""

    def test_deletes_expected_directories(self):
        build = Build("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        storage.extract_artifact(build, jenkins.download_artifact(build))

        storage.delete(build)

        directories = [
            f"{storage.root}/binpkgs/{build}",
            f"{storage.root}/etc-portage/{build}",
            f"{storage.root}/repos/{build}",
            f"{storage.root}/var-lib-portage/{build}",
        ]
        for directory in directories:
            with self.subTest(directory=directory):
                self.assertIs(os.path.exists(directory), False)


class StorageExtractArtifactTestCase(TestCase):
    """Tests for Storage.extract_artifact"""

    def test_does_not_extract_already_pulled_build(self):
        build = Build("build.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        storage.extract_artifact(build, jenkins.download_artifact(build))
        assert storage.pulled(build)

        # extract won't be able to extract this
        byte_stream_mock = iter([b""])

        try:
            storage.extract_artifact(build, byte_stream_mock)
        except tarfile.ReadError:
            self.fail("extract_artifact() should not have attempted to extract")

    def test_extracts_bytesteam_and_content(self):
        build = Build("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)

        storage.extract_artifact(build, jenkins.download_artifact(build))

        self.assertIs(storage.pulled(build), True)

    def test_uses_hard_link_if_previous_build_exists(self):
        previous_build = Build("babette.19")
        storage = Storage(self.tmpdir)
        jenkins = MockJenkins.from_settings(TEST_SETTINGS)
        timestamp = jenkins.artifact_builder.timer
        storage.extract_artifact(
            previous_build, jenkins.download_artifact(previous_build)
        )

        current_build = Build("babette.20")

        # Reverse time so we have duplicate mtimes
        jenkins.artifact_builder.timer = timestamp
        storage.extract_artifact(
            current_build,
            jenkins.download_artifact(current_build),
            previous=previous_build,
        )

        for item in Content:
            dst_path = storage.get_path(current_build, item)
            self.assertIs(dst_path.exists(), True)

        package_index = storage.get_path(current_build, Content.BINPKGS) / "Packages"
        self.assertEqual(package_index.stat().st_nlink, 2)


class StorageGetPackagesTestCase(TestCase):
    """tests for the Storage.get_packages() method"""

    def setUp(self):
        super().setUp()

        self.build = BuildFactory()
        self.publisher.pull(self.build)
        self.storage = self.publisher.storage

    def test_should_return_list_of_packages_from_index(self):
        packages = self.storage.get_packages(self.build)

        self.assertEqual(len(packages), len(PACKAGE_INDEX))
        package = packages[3]
        self.assertEqual(package.cpv, "app-crypt/gpgme-1.14.0")
        self.assertEqual(package.repo, "gentoo")
        self.assertEqual(package.path, "app-crypt/gpgme/gpgme-1.14.0-1.xpak")
        self.assertEqual(package.build_id, 1)
        self.assertEqual(package.size, 484)
        self.assertEqual(package.build_time, 0)

    def test_should_raise_lookuperror_when_index_file_missing(self):
        index_file = self.storage.get_path(self.build, Content.BINPKGS) / "Packages"
        index_file.unlink()

        with self.assertRaises(LookupError):
            self.storage.get_packages(self.build)


class StorageGetMetadataTestCase(TestCase):
    """tests for the Storage.get_metadata() method"""

    def setUp(self):
        super().setUp()

        self.build = BuildFactory()
        self.timestamp = int(self.artifact_builder.timestamp / 1000)
        self.artifact_builder.build(self.build, "dev-libs/cyrus-sasl-2.1.28-r1")
        self.artifact_builder.build(self.build, "net-libs/nghttp2-1.47.0")
        self.artifact_builder.build(self.build, "sys-libs/glibc-2.34-r9")
        self.publisher.pull(self.build)
        self.storage = self.publisher.storage

    def test_should_return_gbpmetadata_when_gbp_json_exists(self):
        metadata = self.storage.get_metadata(self.build)

        expected = GBPMetadata(
            build_duration=124,
            packages=PackageMetadata(
                total=7,
                size=3807,
                built=[
                    Package(
                        cpv="dev-libs/cyrus-sasl-2.1.28-r1",
                        repo="gentoo",
                        path="dev-libs/cyrus-sasl/cyrus-sasl-2.1.28-r1-1.xpak",
                        build_id=1,
                        size=841,
                        build_time=self.timestamp + 10,
                    ),
                    Package(
                        cpv="net-libs/nghttp2-1.47.0",
                        repo="gentoo",
                        path="net-libs/nghttp2/nghttp2-1.47.0-1.xpak",
                        build_id=1,
                        size=529,
                        build_time=self.timestamp + 20,
                    ),
                    Package(
                        cpv="sys-libs/glibc-2.34-r9",
                        repo="gentoo",
                        path="sys-libs/glibc/glibc-2.34-r9-1.xpak",
                        build_id=1,
                        size=484,
                        build_time=self.timestamp + 30,
                    ),
                ],
            ),
        )
        self.assertEqual(metadata, expected)

    def test_should_raise_lookuperror_when_file_does_not_exist(self):
        path = self.storage.get_path(self.build, Content.BINPKGS) / "gbp.json"
        path.unlink()

        with self.assertRaises(LookupError) as context:
            self.storage.get_metadata(self.build)

        exception = context.exception
        self.assertEqual(exception.args, (f"gbp.json does not exist for {self.build}",))


class StorageSetMetadataTestCase(TestCase):
    """tests for the Storage.set_metadata() method"""

    def setUp(self):
        super().setUp()
        self.build = BuildFactory()
        self.publisher.pull(self.build)
        self.storage = self.publisher.storage
        self.path = self.storage.get_path(self.build, Content.BINPKGS) / "gbp.json"

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
        self.storage.set_metadata(self.build, gbp_metadata)

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


class StorageReposTestCase(TestCase):
    def test(self):
        build = BuildFactory()
        self.publisher.pull(build)

        repos = self.publisher.storage.repos(build)

        self.assertEqual(repos, {"gentoo", "marduk"})

    def test_raise_exception_when_not_pulled(self):
        build = BuildFactory()

        with self.assertRaises(FileNotFoundError) as context:
            self.publisher.storage.repos(build)

        self.assertEqual(context.exception.args, ("The build has not been pulled",))


class StorageTaggingTestCase(TestCase):
    def test_can_create_tagged_directory_symlinks(self):
        build = BuildFactory()
        self.publisher.pull(build)

        self.publisher.storage.tag(build, "prod")

        for item in Content:
            target_path = self.publisher.storage.get_path(build, item)
            source_path = (
                self.publisher.storage.root / item.value / f"{build.machine}@prod"
            )

            self.assertTrue(source_path.is_symlink())
            self.assertEqual(source_path.resolve(), target_path)

    def test_can_retag(self):
        build1 = BuildFactory()
        self.publisher.pull(build1)
        self.publisher.storage.tag(build1, "prod")

        build2 = BuildFactory()
        self.publisher.pull(build2)
        self.publisher.storage.tag(build2, "prod")

        for item in Content:
            target_path = self.publisher.storage.get_path(build2, item)
            source_path = (
                self.publisher.storage.root / item.value / f"{build2.machine}@prod"
            )

            self.assertTrue(source_path.is_symlink())
            self.assertEqual(source_path.resolve(), target_path)

    def test_can_untag(self):
        build = BuildFactory()
        self.publisher.pull(build)
        self.publisher.storage.tag(build, "prod")

        self.publisher.storage.untag(build.machine, "prod")

        for item in Content:
            target_path = self.publisher.storage.get_path(build, item)
            source_path = (
                self.publisher.storage.root / item.value / f"{build.machine}@prod"
            )

            self.assertFalse(source_path.exists())
            self.assertTrue(target_path.exists())

    def test_can_untag_if_no_such_tag_exists(self):
        """Removing a non-existant tag should fail silently"""
        build = BuildFactory()
        self.publisher.pull(build)
        self.publisher.storage.untag(build, "prod")

    def test_non_published_builds_have_no_tags(self):
        build = BuildFactory()
        self.publisher.pull(build)

        tags = self.publisher.storage.get_tags(build)

        self.assertEqual(tags, [])

    def test_builds_can_have_multiple_tags(self):
        build = BuildFactory()
        self.publisher.pull(build)
        self.publisher.storage.tag(build, "prod")
        self.publisher.storage.tag(build, "albert")

        tags = self.publisher.storage.get_tags(build)

        self.assertEqual(tags, ["albert", "prod"])

        self.publisher.publish(build)
        tags = self.publisher.storage.get_tags(build)

        self.assertEqual(tags, ["", "albert", "prod"])

    def test_published_builds_have_the_empty_tag(self):
        build = BuildFactory()
        self.publisher.publish(build)

        tags = self.publisher.storage.get_tags(build)

        self.assertEqual(tags, [""])

    def test_unpulled_builds_have_no_tags(self):
        build = BuildFactory()

        tags = self.publisher.storage.get_tags(build)

        self.assertEqual(tags, [])

    def test_partially_tagged_directories_are_not_tagged(self):
        build = BuildFactory()
        self.publisher.pull(build)
        self.publisher.storage.tag(build, "prod")
        self.publisher.storage.tag(build, "albert")

        # Remove one of the symlinks
        broken = (
            self.publisher.storage.root / Content.REPOS.value / f"{build.machine}@prod"
        )
        broken.unlink()

        tags = self.publisher.storage.get_tags(build)

        self.assertEqual(tags, ["albert"])


class StorageResolveTagTestCase(TestCase):
    """Tests for the Storage.resolve_tag method"""

    def test_resolve_tag_returns_the_build_that_it_belongs_to(self):
        build = BuildFactory()
        self.publisher.pull(build)
        self.publisher.storage.tag(build, "prod")

        tag = f"{build.machine}@prod"
        target = self.publisher.storage.resolve_tag(tag)

        self.assertEqual(target, build)

    def test_resolve_tag_raises_exception_when_given_invalid_tag(self):
        with self.assertRaises(ValueError) as context:
            self.publisher.storage.resolve_tag("notatag")

        self.assertEqual(context.exception.args[0], "Invalid tag: notatag")

    def test_resolve_tag_raises_exception_when_build_doesnt_exist(self):
        build = BuildFactory(machine="lighthouse")
        self.publisher.pull(build)
        self.publisher.storage.tag(build, "prod")

        self.publisher.storage.delete(build)
        with self.assertRaises(FileNotFoundError) as context:
            self.publisher.storage.resolve_tag("lighthouse@prod")

        self.assertEqual(
            context.exception.args[0],
            "Tag is broken or does not exist: lighthouse@prod",
        )


class QuickCheckTestCase(TestCase):
    """Tests for the quick_check() helper method"""

    def test(self):
        timestamp = datetime.datetime(2021, 10, 30, 7, 10, 39)
        file1 = str(self.create_file("foo", b"test", timestamp))
        file2 = str(self.create_file("bar", b"xxxx", timestamp))

        result = quick_check(file1, file2)

        self.assertIs(result, True)

    def test_should_return_false_when_file_does_not_exist(self):
        timestamp = datetime.datetime(2021, 10, 30, 7, 10, 39)
        file1 = str(self.create_file("foo", b"test", timestamp))
        file2 = str(self.tmpdir / "bogus")

        result = quick_check(file1, file2)

        self.assertIs(result, False)

    def test_should_return_false_when_mtimes_differ(self):
        timestamp1 = datetime.datetime(2021, 10, 30, 7, 10, 39)
        timestamp2 = datetime.datetime(2021, 10, 30, 7, 10, 40)
        file1 = str(self.create_file("foo", b"test", timestamp1))
        file2 = str(self.create_file("bar", b"test", timestamp2))

        result = quick_check(file1, file2)

        self.assertIs(result, False)

    def test_should_return_false_when_sizes_differ(self):
        timestamp = datetime.datetime(2021, 10, 30, 7, 10, 39)
        file1 = str(self.create_file("foo", b"test", timestamp))
        file2 = str(self.create_file("bar", b"tst", timestamp))

        result = quick_check(file1, file2)

        self.assertIs(result, False)
