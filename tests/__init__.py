"""Tests for gentoo build publisher"""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name
import datetime as dt
import io
import json
import logging
import math
import os
import tarfile
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Union
from unittest import TestCase as UnitTestTestCase
from unittest import mock

import django.test

from gentoo_build_publisher import publisher
from gentoo_build_publisher.jenkins import Jenkins, JenkinsConfig, JenkinsMetadata
from gentoo_build_publisher.types import Build, Content, Package
from gentoo_build_publisher.utils import cpv_to_path

BASE_DIR = Path(__file__).resolve().parent / "data"

# This is the default list of packages (in order) stored in the artifacts
PACKAGE_INDEX: list[str] = [
    "acct-group/sgx-0",
    "app-admin/perl-cleaner-2.30",
    "app-arch/unzip-6.0_p26",
    "app-crypt/gpgme-1.14.0",
]


logging.basicConfig(handlers=[logging.NullHandler()])


class TestCase(django.test.TestCase):
    def setUp(self):
        # pylint: disable=import-outside-toplevel,cyclic-import
        from .factories import BuildPublisherFactory

        super().setUp()

        tmpdir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(tmpdir.cleanup)
        self.tmpdir = Path(tmpdir.name)
        patch = mock.patch.dict(
            os.environ,
            {
                "BUILD_PUBLISHER_STORAGE_PATH": tmpdir.name,
                "BUILD_PUBLISHER_JENKINS_BASE_URL": "https://jenkins.invalid/",
                "BUILD_PUBLISHER_RECORDS_BACKEND": "django",
            },
        )
        self.addCleanup(patch.stop)
        patch.start()

        self.publisher = BuildPublisherFactory()
        patch = mock.patch.object(publisher, "_PUBLISHER", new=self.publisher)
        self.addCleanup(patch.stop)
        patch.start()

        self.artifact_builder = self.publisher.jenkins.artifact_builder

    def create_file(self, name, content=b"", mtime=None):
        path = self.tmpdir / name

        with path.open("wb") as outfile:
            outfile.write(content)

        if mtime is not None:
            stat = os.stat(path)
            atime = stat.st_atime
            os.utime(path, times=(atime, mtime.timestamp()))

        return path


def parametrized(lists_of_args: Iterable[Iterable[Any]]) -> Callable:
    def dec(func: Callable):
        @wraps(func)
        def wrapper(self: UnitTestTestCase, *args: Any, **kwargs: Any) -> None:
            for list_of_args in lists_of_args:
                name = ",".join(str(i) for i in list_of_args)
                with self.subTest(name):
                    func(self, *args, *list_of_args, **kwargs)

        return wrapper

    return dec


def test_data(filename):
    """Return all the data in filename"""
    with open(BASE_DIR / filename, "rb") as file_obj:
        return file_obj.read()


class MockJenkins(Jenkins):
    """Jenkins with requests mocked out"""

    mock_get = None
    get_build_logs_mock_get = None

    def __init__(self, config: JenkinsConfig):

        super().__init__(config)

        self.artifact_builder = ArtifactBuilder()
        self.scheduled_builds: list[str] = []

    def download_artifact(self, build: Build):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.iter_content.side_effect = (
                lambda *args, **kwargs: self.artifact_builder.get_artifact(build)
            )
            self.mock_get = mock_get
            return super().download_artifact(build)

    def get_logs(self, build: Build):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.text = "foo\n"
            self.get_build_logs_mock_get = mock_get

            return super().get_logs(build)

    def get_metadata(self, build: Build) -> JenkinsMetadata:
        build_time = self.artifact_builder.build_info(build).build_time
        return JenkinsMetadata(duration=124, timestamp=build_time)

    def schedule_build(self, machine: str) -> str:
        self.scheduled_builds.append(machine)

        return str(self.config.base_url / "job" / machine / "build")


class PackageStatus(Enum):
    ADDED = auto()
    REMOVED = auto()


@dataclass
class BuildInfo:
    build_time: int
    package_info: list[tuple[Package, PackageStatus]] = field(default_factory=list)


class ArtifactBuilder:
    """Build CI/CD artifacts dynamically"""

    def __init__(self, initial_packages=None, timestamp=None):
        if timestamp is None:
            self.timestamp = int(dt.datetime.utcnow().timestamp() * 1000)
        else:
            self.timestamp = timestamp

        self.timer = int(self.timestamp / 1000)

        if initial_packages is None:
            self.initial_packages = [*PACKAGE_INDEX]
        else:
            self.initial_packages = initial_packages

        self._builds: dict[str, BuildInfo] = {}

    def build(  # pylint: disable=too-many-arguments
        self,
        build: Build,
        cpv: str,
        repo="gentoo",
        build_id: int = 1,
        build_time: int | None = None,
    ) -> Package:
        """Pretend we've built a package and add it to the package index"""
        build_info = self.build_info(build)

        if build_time is None:
            timestamp = self.advance()
            build_time = timestamp

        path = cpv_to_path(cpv, build_id)
        size = len(cpv) ** 2
        package = Package(cpv, repo, path, build_id, size, build_time)
        build_info.package_info.append((package, PackageStatus.ADDED))

        return package

    def build_info(self, build: Build) -> BuildInfo:
        """Return the BuildInfo for the given build"""
        return self._builds.setdefault(build.id, BuildInfo(self.timer * 1000, []))

    def remove(self, build: Build, package: Package):
        """Remove a package from the build"""
        build_info = self.build_info(build)

        build_info.package_info.append((package, PackageStatus.REMOVED))

    def get_artifact(self, build: Build) -> io.BytesIO:
        """Return a file-like object representing a CI/CD artifact"""
        tar_file = io.BytesIO()
        packages = self.get_packages_for_build(build)

        with tarfile.open("build.tar.gz", "x:gz", tar_file) as tarchive:

            timestamp = self.advance()
            self.add_to_tarchive(
                tarchive,
                "binpkgs/Packages",
                self.index(packages).encode("utf-8"),
                mtime=timestamp,
            )

            for package in packages:
                self.add_to_tarchive(
                    tarchive, f"binpkgs/{package.path}", b"", mtime=package.build_time
                )

            for item in Content:
                tar_info = tarfile.TarInfo(item.value)
                tar_info.type = tarfile.DIRTYPE
                tar_info.mode = 0o0755
                tarchive.addfile(tar_info)

                if item is Content.REPOS:
                    # Fake some repos dirs
                    for repo in ["gentoo", "marduk"]:
                        tar_info = tarfile.TarInfo(f"{item.value}/{repo}")
                        tar_info.type = tarfile.DIRTYPE
                        tar_info.mode = 0o0755
                        tarchive.addfile(tar_info)

        tar_file.seek(0)
        self.timestamp = self.timer * 1000

        return tar_file

    def get_packages_for_build(self, build: Build) -> list[Package]:
        # First constuct the list from the initially installed packages and give them a
        # build time of 0
        packages = [
            Package(i, "gentoo", cpv_to_path(i), 1, len(i) ** 2, 0)
            for i in self.initial_packages
        ]

        # Next iterate on dict of builds for this build's machine and add/remove their
        # packages from the list. Note we are totally relying on the fact that dicts are
        # ordered here
        build_machine = build.machine
        for build_id, build_data in self._builds.items():
            if Build(build_id).machine != build_machine:
                continue

            for package, status in build_data.package_info:
                if status is PackageStatus.ADDED:
                    packages.append(package)

                else:
                    packages.remove(package)

            if build_id == build.id:
                break

        return packages

    @staticmethod
    def index(packages: list[Package]) -> str:
        """Return the package index a-la Packages"""
        strings = [
            (
                "\n"
                f"BUILD_ID: {package.build_id}\n"
                f"CPV: {package.cpv}\n"
                f"SIZE: {package.size}\n"
                f"REPO: {package.repo}\n"
                f"PATH: {cpv_to_path(package.cpv, package.build_id)}\n"
                f"BUILD_TIME: {package.build_time}\n"
            )
            for package in sorted(packages, key=lambda p: p.cpv)
        ]

        return "".join(["Ignore Preamble\n", *strings])

    @staticmethod
    def add_to_tarchive(
        tarchive: tarfile.TarFile,
        arcname: str,
        content: bytes,
        mtime: int | None = None,
    ):
        file_obj = io.BytesIO(content)
        tar_info = tarfile.TarInfo(arcname)
        tar_info.size = len(content)
        tar_info.mode = 0o0644

        if mtime is None:
            tar_info.mtime = int(dt.datetime.utcnow().timestamp())
        else:
            tar_info.mtime = mtime

        tarchive.addfile(tar_info, file_obj)

    def advance(self, seconds: int = 10) -> int:
        self.timer += seconds

        return self.timer
