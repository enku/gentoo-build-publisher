"""I heard you like tests..."""
# pylint: disable=missing-docstring
import tarfile
from unittest import TestCase, mock

from gentoo_build_publisher.types import Content, Package

from . import ArtifactBuilder, BuildInfo, PackageStatus
from .factories import BuildFactory


class ArtifactBuilderTestCase(TestCase):
    def setUp(self):
        super().setUp()

        self.builder = ArtifactBuilder(initial_packages=[])

    def test_timestamp(self):
        with mock.patch("tests.time.time", return_value=1645750289.719158):
            builder = ArtifactBuilder()

        self.assertEqual(builder.timestamp, 1645750289719)

    def test_advance(self):
        timer = self.builder.timer

        result = self.builder.advance(450)

        self.assertEqual(result, timer + 450)
        self.assertEqual(self.builder.timer, result)

    def test_build_should_add_to_packages(self):
        timer = self.builder.timer
        build = BuildFactory()
        package = self.builder.build(
            build, "app-vim/gentoo-syntax-1", repo="marduk", build_id=35
        )

        expected = Package(
            "app-vim/gentoo-syntax-1",
            "marduk",
            "app-vim/gentoo-syntax/gentoo-syntax-1-35.xpak",
            35,
            529,
            timer + 10,
        )
        self.assertEqual(package, expected)
        build_info = self.builder.build_info(build)
        added = [i[0] for i in build_info.package_info if i[1] is PackageStatus.ADDED]
        self.assertEqual(added, [expected])

    def test_remove_should_remove_package(self):
        build = BuildFactory()
        builder = ArtifactBuilder()
        package = builder.get_packages_for_build(build)[0]

        builder.remove(build, package)

        self.assertFalse(package in builder.get_packages_for_build(build))

    def test_get_artifact(self):
        build = BuildFactory()
        self.builder.build(build, "app-vim/gentoo-syntax-1")

        artifact = self.builder.get_artifact(build)

        with tarfile.TarFile.open(
            "build.tar.gz", mode="r", fileobj=artifact
        ) as tar_file:
            artifact_contents = [i.path for i in tar_file.getmembers()]

        for item in Content:
            self.assertTrue(item.value in artifact_contents)

        self.assertTrue("binpkgs/Packages" in artifact_contents)

    def test_downloading_artifact_should_advance_timestamp(self):
        build = BuildFactory()
        builder = ArtifactBuilder(timestamp=0)
        self.assertEqual(builder.timestamp, 0)

        builder.get_artifact(build)

        timestamp = builder.timestamp
        self.assertNotEqual(timestamp, 0)

        builder.get_artifact(build)
        self.assertGreater(builder.timestamp, timestamp)

    def test_build_info_with_new_build(self):
        build = BuildFactory()
        build_info = self.builder.build_info(build)

        expected = BuildInfo(build_time=self.builder.timer * 1000, package_info=[])
        self.assertEqual(expected, build_info)

    def test_build_info_with_existing_build(self):
        build = BuildFactory()
        self.builder.build(build, "app-vim/gentoo-syntax-1")
        build_info = self.builder.build_info(build)

        expected = BuildInfo(
            build_time=(self.builder.timer - 10) * 1000,
            package_info=[
                (
                    Package(
                        "app-vim/gentoo-syntax-1",
                        "gentoo",
                        "app-vim/gentoo-syntax/gentoo-syntax-1-1.xpak",
                        1,
                        529,
                        self.builder.timer,
                    ),
                    PackageStatus.ADDED,
                )
            ],
        )
        self.assertEqual(expected, build_info)

    def test_get_packages_for_build(self):
        builder = ArtifactBuilder()

        # Do build1
        build1 = BuildFactory()
        # Remove acct-group/sgx
        existing_pkg = builder.get_packages_for_build(build1)[0]
        builder.remove(build1, existing_pkg)
        # add openssh-8.9
        openssh = builder.build(build1, "net-misc/openssh-8.9_p1-1")
        # add dbus
        builder.build(build1, "sys-apps/dbus-1.12.22-1")

        # Do build2
        build2 = BuildFactory()
        # downgrade openssh
        builder.build(build2, "net-misc/openssh-8.8_p1-r4-1")
        builder.remove(build2, openssh)
        # add libffi
        builder.build(build2, "dev-libs/libffi-3.3-r2-1")

        build1_pkgs = set(i.cpv for i in builder.get_packages_for_build(build1))
        build2_pkgs = set(i.cpv for i in builder.get_packages_for_build(build2))

        self.assertEqual(
            {
                "app-admin/perl-cleaner-2.30",
                "app-arch/unzip-6.0_p26",
                "app-crypt/gpgme-1.14.0",
                "net-misc/openssh-8.9_p1-1",
                "sys-apps/dbus-1.12.22-1",
            },
            build1_pkgs,
        )

        self.assertEqual(
            {
                "app-admin/perl-cleaner-2.30",
                "app-arch/unzip-6.0_p26",
                "app-crypt/gpgme-1.14.0",
                "dev-libs/libffi-3.3-r2-1",
                "net-misc/openssh-8.8_p1-r4-1",
                "sys-apps/dbus-1.12.22-1",
            },
            build2_pkgs,
        )