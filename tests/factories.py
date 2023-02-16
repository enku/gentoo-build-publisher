"""Test factories for GBP"""
# pylint: disable=missing-docstring,too-few-public-methods
import datetime as dt
import io
import tarfile
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto

import factory
from django.utils import timezone

from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.publisher import BuildPublisher, get_publisher
from gentoo_build_publisher.records import BuildRecord, Records
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage
from gentoo_build_publisher.types import Build, Content, Package
from gentoo_build_publisher.utils import cpv_to_path

from . import MockJenkins


class PackageStatus(Enum):
    ADDED = auto()
    REMOVED = auto()


@dataclass
class BuildInfo:
    build_time: int
    package_info: list[tuple[Package, PackageStatus]] = field(default_factory=list)


class BuildModelFactory(factory.django.DjangoModelFactory):
    """BuildModel factory"""

    class Meta:
        model = BuildModel

    machine = "babette"
    build_id = factory.Sequence(str)
    submitted = factory.LazyFunction(timezone.now)
    completed = None


class BuildFactory(factory.Factory):
    """Build factory"""

    class Meta:
        model = Build

    machine = "babette"
    build_id = factory.Sequence(str)

    @classmethod
    def buncha_builds(
        cls,
        machines: list[str],
        end_date: dt.datetime,
        num_days: int,
        per_day: int,
    ) -> defaultdict[str, list[Build]]:
        publisher = get_publisher()
        buildmap = defaultdict(list)

        for i in reversed(range(num_days)):
            day = end_date - dt.timedelta(days=i)
            for machine in machines:
                builds = cls.create_batch(per_day, machine=machine)

                for build in builds:
                    publisher.records.save(publisher.record(build), submitted=day)

                buildmap[machine].extend(builds)

        return buildmap


class BuildRecordFactory(BuildFactory):
    """BuildRecord Factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = BuildRecord

    submitted = None
    completed = None
    note = None
    logs = None
    keep = False


class BuildPublisherFactory(factory.Factory):
    """BuildPublisher factory"""

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        model = BuildPublisher

    jenkins = factory.LazyAttribute(
        lambda _: MockJenkins.from_settings(Settings.from_environ())
    )
    storage = factory.LazyAttribute(
        lambda _: Storage.from_settings(Settings.from_environ())
    )
    records = factory.LazyAttribute(
        lambda _: Records.from_settings(Settings.from_environ())
    )


# This is the default list of packages (in order) stored in the artifacts
PACKAGE_INDEX: list[str] = [
    "acct-group/sgx-0",
    "app-admin/perl-cleaner-2.30",
    "app-arch/unzip-6.0_p26",
    "app-crypt/gpgme-1.14.0",
]


class ArtifactFactory:
    """Build CI/CD artifacts dynamically"""

    def __init__(
        self, initial_packages: list[str] | None = None, timestamp: int | None = None
    ) -> None:
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
        repo: str = "gentoo",
        build_id: int = 1,
        build_time: int | None = None,
    ) -> Package:
        """Pretend we've built a package and add it to the package index"""
        build_info = self.build_info(build)

        if build_time is None:
            build_time = self.advance()

        path = cpv_to_path(cpv, build_id)
        size = len(cpv) ** 2
        package = Package(cpv, repo, path, build_id, size, build_time)
        build_info.package_info.append((package, PackageStatus.ADDED))

        return package

    def build_info(self, build: Build) -> BuildInfo:
        """Return the BuildInfo for the given build"""
        return self._builds.setdefault(build.id, BuildInfo(self.timer * 1000, []))

    def remove(self, build: Build, package: Package) -> None:
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
            if Build.from_id(build_id).machine != build_machine:
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
    ) -> None:
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
