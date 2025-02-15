"""Tests for the storage type"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import json
import os
import tarfile
from dataclasses import replace
from pathlib import Path

import unittest_fixtures as fixture

from gentoo_build_publisher import publisher, utils
from gentoo_build_publisher.jenkins import Jenkins
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import (
    Storage,
    make_package_from_lines,
    make_packages,
)
from gentoo_build_publisher.types import (
    Build,
    Content,
    GBPMetadata,
    Package,
    PackageMetadata,
)

from . import TestCase, data
from .factories import PACKAGE_INDEX, BuildFactory
from .helpers import MockJenkins

FixtureOptions = fixture.FixtureOptions
Fixtures = fixture.Fixtures

TEST_SETTINGS = Settings(
    STORAGE_PATH=Path("/dev/null"), JENKINS_BASE_URL="https://jenkins.invalid/"
)


@fixture.requires("environ", "tmpdir")
class StorageFromSettings(TestCase):
    options = {"environ": {}, "environ_clear": False}

    def test(self) -> None:
        """Should instantiate Storage from settings"""
        # Given the settings
        settings = replace(TEST_SETTINGS, STORAGE_PATH=self.fixtures.tmpdir)

        # When we instantiate Storage.from_settings
        storage = Storage.from_settings(settings)

        # Then we get a Storage instance with attributes from settings
        self.assertIsInstance(storage, Storage)
        self.assertEqual(storage.root, self.fixtures.tmpdir)


@fixture.depends("tmpdir")
def storage_fixture(_options: FixtureOptions, fixtures: Fixtures) -> Storage:
    root = fixtures.tmpdir / "root"
    return Storage(root)


@fixture.depends("tmpdir")
def jenkins_fixture(_options: FixtureOptions, fixtures: Fixtures) -> Jenkins:
    root = fixtures.tmpdir / "root"
    settings = replace(TEST_SETTINGS, STORAGE_PATH=root)

    return MockJenkins.from_settings(settings)


@fixture.requires("build", storage_fixture, jenkins_fixture)
class StorageDownloadArtifactTestCase(TestCase):
    """Tests for Storage.download_artifact"""

    def has_content(self, build: Build, content: Content) -> bool:
        storage: Storage = self.fixtures.storage
        return storage.get_path(build, content).is_dir()

    def download_and_extract(self, build: Build) -> None:
        self.fixtures.storage.extract_artifact(
            build, self.fixtures.jenkins.download_artifact(build)
        )

    def test_extract_artifact_moves_repos_and_binpkgs(self) -> None:
        """Should extract artifacts and move to repos/ and binpkgs/"""
        self.download_and_extract(self.fixtures.build)

        self.assertTrue(self.has_content(self.fixtures.build, Content.REPOS))
        self.assertTrue(self.has_content(self.fixtures.build, Content.BINPKGS))

    def test_extract_artifact_creates_etc_portage_dir(self) -> None:
        """Should extract artifacts and move to etc-portage/"""
        self.download_and_extract(self.fixtures.build)

        self.assertTrue(self.has_content(self.fixtures.build, Content.ETC_PORTAGE))

    def test_extract_artifact_creates_var_lib_portage_dir(self) -> None:
        """Should extract artifacts and move to var-lib-portage/"""
        self.download_and_extract(self.fixtures.build)

        self.assertTrue(self.has_content(self.fixtures.build, Content.VAR_LIB_PORTAGE))

    def test_extract_artifact_should_remove_dst_if_it_already_exists(self) -> None:
        # When when one of the target paths already exist
        path = self.fixtures.storage.get_path(self.fixtures.build, Content.BINPKGS)
        path.mkdir(parents=True)
        orphan = path / "this should not be here"
        orphan.touch()

        # And we extract the build
        self.download_and_extract(self.fixtures.build)

        # Then the orphaned path is removed
        self.assertIs(path.exists(), True)
        self.assertIs(orphan.exists(), False, orphan)


@fixture.requires("tmpdir")
class StoragePublishTestCase(TestCase):
    """Tests for Storage.publish"""

    def test_publish_raises_exception_repos_dir_does_not_exist(self) -> None:
        """Should raise an exception if the build has not been pulled"""
        # Given the build
        build = Build("babette", "193")

        # Given the storage
        storage = Storage(self.fixtures.tmpdir)

        # Then an exception is raised
        with self.assertRaises(FileNotFoundError):
            # When we call publish
            storage.publish(build)


@fixture.requires("environ", "storage", "build", "settings", "jenkins")
class StoragePublishedTestCase(TestCase):
    """Tests for Storage.published"""

    def download_and_extract(self, build: Build) -> None:
        self.fixtures.storage.extract_artifact(
            build, self.fixtures.jenkins.download_artifact(build)
        )

    def test_published_true(self) -> None:
        """.published should return True when published"""
        self.download_and_extract(self.fixtures.build)
        self.fixtures.storage.publish(self.fixtures.build)

        published = self.fixtures.storage.published(self.fixtures.build)

        self.assertTrue(published)

    def test_published_false(self) -> None:
        """.published should return False when not published"""
        published = self.fixtures.storage.published(self.fixtures.build)

        self.assertFalse(published)

    def test_other_published(self) -> None:
        self.download_and_extract(self.fixtures.build)
        self.fixtures.storage.publish(self.fixtures.build)

        # Given the second build published
        build2 = Build("babette", "194")
        self.download_and_extract(build2)
        self.fixtures.storage.publish(build2)

        # Then published returns True on the second build
        self.assertTrue(self.fixtures.storage.published(build2))

        # And False on the first build
        self.assertFalse(self.fixtures.storage.published(self.fixtures.build))


@fixture.requires("tmpdir")
class StorageDeleteTestCase(TestCase):
    """Tests for Storage.delete"""

    def test_deletes_expected_directories(self) -> None:
        build = Build("babette", "19")
        root = self.fixtures.tmpdir / "root"
        storage = Storage(root)
        settings = replace(TEST_SETTINGS, STORAGE_PATH=root)
        jenkins = MockJenkins.from_settings(settings)
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


@fixture.requires("build", "storage", jenkins_fixture)
class StorageExtractArtifactTestCase(TestCase):
    """Tests for Storage.extract_artifact"""

    def test_does_not_extract_already_pulled_build(self) -> None:
        self.fixtures.storage.extract_artifact(
            self.fixtures.build,
            self.fixtures.jenkins.download_artifact(self.fixtures.build),
        )
        assert self.fixtures.storage.pulled(self.fixtures.build)

        # extract won't be able to extract this
        byte_stream_mock = iter([b""])

        try:
            self.fixtures.storage.extract_artifact(
                self.fixtures.build, byte_stream_mock
            )
        except tarfile.ReadError:
            self.fail("extract_artifact() should not have attempted to extract")

    def test_extracts_bytesteam_and_content(self) -> None:
        self.fixtures.storage.extract_artifact(
            self.fixtures.build,
            self.fixtures.jenkins.download_artifact(self.fixtures.build),
        )
        self.assertIs(self.fixtures.storage.pulled(self.fixtures.build), True)

    def test_uses_hard_link_if_previous_build_exists(self) -> None:
        previous_build = Build("babette", "19")
        timestamp = self.fixtures.jenkins.artifact_builder.timer
        self.fixtures.storage.extract_artifact(
            previous_build, self.fixtures.jenkins.download_artifact(previous_build)
        )

        current_build = Build("babette", "20")

        # Reverse time so we have duplicate mtimes
        self.fixtures.jenkins.artifact_builder.timer = timestamp
        self.fixtures.storage.extract_artifact(
            current_build,
            self.fixtures.jenkins.download_artifact(current_build),
            previous=previous_build,
        )

        for item in Content:
            dst_path = self.fixtures.storage.get_path(current_build, item)
            self.assertIs(dst_path.exists(), True)

        package_index = (
            self.fixtures.storage.get_path(current_build, Content.BINPKGS) / "Packages"
        )
        self.assertEqual(package_index.stat().st_nlink, 2)


@fixture.requires("publisher", "build")
class StorageGetPackagesTestCase(TestCase):
    """tests for the Storage.get_packages() method"""

    def test_should_return_list_of_packages_from_index(self) -> None:
        publisher.pull(self.fixtures.build)
        packages = publisher.storage.get_packages(self.fixtures.build)

        self.assertEqual(len(packages), len(PACKAGE_INDEX))
        package = packages[3]
        self.assertEqual(package.cpv, "app-crypt/gpgme-1.14.0")
        self.assertEqual(package.repo, "gentoo")
        self.assertEqual(package.path, "app-crypt/gpgme/gpgme-1.14.0-1.gpkg.tar")
        self.assertEqual(package.build_id, 1)
        self.assertEqual(package.size, 484)
        self.assertEqual(package.build_time, 0)

    def test_should_raise_lookuperror_when_index_file_missing(self) -> None:
        publisher.pull(self.fixtures.build)
        index_file = (
            publisher.storage.get_path(self.fixtures.build, Content.BINPKGS)
            / "Packages"
        )
        index_file.unlink()

        with self.assertRaises(LookupError):
            publisher.storage.get_packages(self.fixtures.build)


@fixture.depends("publisher")
def timestamp_fixture(_options: FixtureOptions, fixtures: Fixtures) -> int:
    return int(fixtures.publisher.jenkins.artifact_builder.timestamp / 1000)


@fixture.depends("publisher")
def artifacts(_options: FixtureOptions, fixtures: Fixtures) -> list[Package]:
    artifact_builder = fixtures.publisher.jenkins.artifact_builder
    a1 = artifact_builder.build(fixtures.build, "dev-libs/cyrus-sasl-2.1.28-r1")
    a2 = artifact_builder.build(fixtures.build, "net-libs/nghttp2-1.47.0")
    a3 = artifact_builder.build(fixtures.build, "sys-libs/glibc-2.34-r9")
    publisher.pull(fixtures.build)

    return [a1, a2, a3]


@fixture.requires("build", "publisher", timestamp_fixture, artifacts)
class StorageGetMetadataTestCase(TestCase):
    """tests for the Storage.get_metadata() method"""

    def test_should_return_gbpmetadata_when_gbp_json_exists(self) -> None:
        metadata = publisher.storage.get_metadata(self.fixtures.build)

        expected = GBPMetadata(
            build_duration=124,
            packages=PackageMetadata(
                total=7,
                size=3807,
                built=[
                    Package(
                        cpv="dev-libs/cyrus-sasl-2.1.28-r1",
                        repo="gentoo",
                        path="dev-libs/cyrus-sasl/cyrus-sasl-2.1.28-r1-1.gpkg.tar",
                        build_id=1,
                        size=841,
                        build_time=self.fixtures.timestamp + 10,
                    ),
                    Package(
                        cpv="net-libs/nghttp2-1.47.0",
                        repo="gentoo",
                        path="net-libs/nghttp2/nghttp2-1.47.0-1.gpkg.tar",
                        build_id=1,
                        size=529,
                        build_time=self.fixtures.timestamp + 20,
                    ),
                    Package(
                        cpv="sys-libs/glibc-2.34-r9",
                        repo="gentoo",
                        path="sys-libs/glibc/glibc-2.34-r9-1.gpkg.tar",
                        build_id=1,
                        size=484,
                        build_time=self.fixtures.timestamp + 30,
                    ),
                ],
            ),
        )
        self.assertEqual(metadata, expected)

    def test_should_raise_lookuperror_when_file_does_not_exist(self) -> None:
        path = (
            publisher.storage.get_path(self.fixtures.build, Content.BINPKGS)
            / "gbp.json"
        )
        path.unlink()

        with self.assertRaises(LookupError) as context:
            publisher.storage.get_metadata(self.fixtures.build)

        exception = context.exception
        self.assertEqual(
            exception.args, (f"gbp.json does not exist for {self.fixtures.build}",)
        )


@fixture.depends("publisher", "build")
def path_fixture(_options: FixtureOptions, fixtures: Fixtures) -> Path:
    publisher.pull(fixtures.build)
    metadata = publisher.storage.get_path(fixtures.build, Content.BINPKGS) / "gbp.json"

    if metadata.exists():
        metadata.unlink()

    return metadata


@fixture.requires("publisher", "build", path_fixture)
class StorageSetMetadataTestCase(TestCase):
    """tests for the Storage.set_metadata() method"""

    def test(self) -> None:
        package_metadata = PackageMetadata(
            total=666,
            size=666,
            built=[
                Package(
                    cpv="sys-foo/bar-1.0",
                    repo="marduk",
                    path="",
                    build_id=1,
                    size=666,
                    build_time=0,
                )
            ],
        )
        gbp_metadata = GBPMetadata(build_duration=666, packages=package_metadata)
        publisher.storage.set_metadata(self.fixtures.build, gbp_metadata)

        with self.fixtures.path.open("r") as json_file:
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


@fixture.requires("publisher")
class StorageReposTestCase(TestCase):
    def test(self) -> None:
        build = BuildFactory()
        publisher.pull(build)

        repos = publisher.storage.repos(build)

        self.assertEqual(repos, {"gentoo", "marduk"})

    def test_raise_exception_when_not_pulled(self) -> None:
        build = BuildFactory()

        with self.assertRaises(FileNotFoundError) as context:
            publisher.storage.repos(build)

        self.assertEqual(context.exception.args, ("The build has not been pulled",))


@fixture.requires("publisher")
class StorageTaggingTestCase(TestCase):
    def test_can_create_tagged_directory_symlinks(self) -> None:
        build = BuildFactory()
        publisher.pull(build)

        publisher.storage.tag(build, "prod")

        for item in Content:
            target_path = publisher.storage.get_path(build, item)
            source_path = publisher.storage.root / item.value / f"{build.machine}@prod"

            self.assertTrue(source_path.is_symlink())
            self.assertEqual(source_path.resolve(), target_path)

    def test_can_retag(self) -> None:
        build1 = BuildFactory()
        publisher.pull(build1)
        publisher.storage.tag(build1, "prod")

        build2 = BuildFactory()
        publisher.pull(build2)
        publisher.storage.tag(build2, "prod")

        for item in Content:
            target_path = publisher.storage.get_path(build2, item)
            source_path = publisher.storage.root / item.value / f"{build2.machine}@prod"

            self.assertTrue(source_path.is_symlink())
            self.assertEqual(source_path.resolve(), target_path)

    def test_can_untag(self) -> None:
        build = BuildFactory()
        publisher.pull(build)
        publisher.storage.tag(build, "prod")

        publisher.storage.untag(build.machine, "prod")

        for item in Content:
            target_path = publisher.storage.get_path(build, item)
            source_path = publisher.storage.root / item.value / f"{build.machine}@prod"

            self.assertFalse(source_path.exists())
            self.assertTrue(target_path.exists())

    def test_can_untag_if_no_such_tag_exists(self) -> None:
        """Removing a non-existent tag should fail silently"""
        build = BuildFactory()
        publisher.pull(build)
        publisher.storage.untag(build, "prod")

    def test_non_published_builds_have_no_tags(self) -> None:
        build = BuildFactory()
        publisher.pull(build)

        tags = publisher.storage.get_tags(build)

        self.assertEqual(tags, [])

    def test_builds_can_have_multiple_tags(self) -> None:
        build = BuildFactory()
        publisher.pull(build)
        publisher.storage.tag(build, "prod")
        publisher.storage.tag(build, "albert")

        tags = publisher.storage.get_tags(build)

        self.assertEqual(tags, ["albert", "prod"])

        publisher.publish(build)
        tags = publisher.storage.get_tags(build)

        self.assertEqual(tags, ["", "albert", "prod"])

    def test_published_builds_have_the_empty_tag(self) -> None:
        build = BuildFactory()
        publisher.publish(build)

        tags = publisher.storage.get_tags(build)

        self.assertEqual(tags, [""])

    def test_unpulled_builds_have_no_tags(self) -> None:
        build = BuildFactory()

        tags = publisher.storage.get_tags(build)

        self.assertEqual(tags, [])

    def test_partially_tagged_directories_are_not_tagged(self) -> None:
        build = BuildFactory()
        publisher.pull(build)
        publisher.storage.tag(build, "prod")
        publisher.storage.tag(build, "albert")

        # Remove one of the symlinks
        broken = publisher.storage.root / Content.REPOS.value / f"{build.machine}@prod"
        broken.unlink()

        tags = publisher.storage.get_tags(build)

        self.assertEqual(tags, ["albert"])


@fixture.requires("publisher")
class StorageResolveTagTestCase(TestCase):
    """Tests for the Storage.resolve_tag method"""

    def test_resolve_tag_returns_the_build_that_it_belongs_to(self) -> None:
        build = BuildFactory()
        publisher.pull(build)
        publisher.storage.tag(build, "prod")

        tag = f"{build.machine}@prod"
        target = publisher.storage.resolve_tag(tag)

        self.assertEqual(target, build)

    def test_resolve_tag_raises_exception_when_given_invalid_tag(self) -> None:
        with self.assertRaises(ValueError) as context:
            publisher.storage.resolve_tag("notatag")

        self.assertEqual(context.exception.args[0], "Invalid tag: notatag")

    def test_resolve_tag_raises_exception_when_build_doesnt_exist(self) -> None:
        build = BuildFactory(machine="lighthouse")
        publisher.pull(build)
        publisher.storage.tag(build, "prod")

        publisher.storage.delete(build)
        with self.assertRaises(FileNotFoundError) as context:
            publisher.storage.resolve_tag("lighthouse@prod")

        self.assertEqual(
            context.exception.args[0],
            "Tag is broken or does not exist: lighthouse@prod",
        )

    def test_resolve_tag_resolves_to_more_than_one_build(self) -> None:
        build1 = BuildFactory()
        publisher.pull(build1)
        build2 = BuildFactory()
        publisher.pull(build2)
        publisher.storage.tag(build1, "prod")
        symlink = publisher.storage.root / "repos" / f"{build1.machine}@prod"
        symlink.unlink()
        symlink.symlink_to(publisher.storage.get_path(build2, Content.REPOS))

        with self.assertRaises(FileNotFoundError):
            publisher.storage.resolve_tag(f"{build1.machine}@prod")

    def test_resolve_tag_when_symlink_points_to_nonbuild(self) -> None:
        build = BuildFactory()
        publisher.pull(build)
        publisher.storage.tag(build, "prod")
        symlink = publisher.storage.root / "repos" / f"{build.machine}@prod"
        symlink.unlink()
        symlink.symlink_to(publisher.storage.root / "repos")

        with self.assertRaises(FileNotFoundError):
            publisher.storage.resolve_tag(f"{build.machine}@prod")


class MakePackageFromLinesTestCase(TestCase):
    """Tests for the make_package_from_lines method"""

    def test(self) -> None:
        result = make_package_from_lines(data.PACKAGE_LINES)

        self.assertIsInstance(result, Package)

    def test_when_line_missing(self) -> None:
        lines = [line for line in data.PACKAGE_LINES if not line.startswith("CPV:")]

        with self.assertRaises(ValueError) as context:
            make_package_from_lines(lines)

        self.assertEqual(context.exception.args[0], "Package lines missing CPV value")


@fixture.requires("publisher")
class MakePackagesTestCase(TestCase):
    """Tests for the make_packages method"""

    def test(self) -> None:
        build = BuildFactory()
        publisher.pull(build)
        index_file = publisher.storage.get_path(build, Content.BINPKGS) / "Packages"

        with index_file.open(encoding="UTF-8") as opened_index_file:
            for line in opened_index_file:  # skip preamble
                if not line.strip():
                    break
            packages = [*make_packages(opened_index_file)]

        self.assertEqual(len(packages), 4)
