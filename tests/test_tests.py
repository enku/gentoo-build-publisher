"""I heard you like tests..."""

# pylint: disable=missing-docstring
import datetime as dt
import tarfile
from unittest import mock

import unittest_fixtures as fixture

from gentoo_build_publisher.types import Content, Package

from .factories import ArtifactFactory, BuildFactory, BuildInfo, PackageStatus
from .helpers import MockJenkinsSession, Tree

FixtureOptions = fixture.FixtureOptions
Fixtures = fixture.Fixtures
TestCase = fixture.BaseTestCase


def builder_fixture(_options: FixtureOptions, _fixtures: Fixtures) -> ArtifactFactory:
    return ArtifactFactory(initial_packages=[])


@fixture.requires(builder_fixture)
class ArtifactFactoryTestCase(TestCase):
    def test_timestamp(self) -> None:
        with mock.patch("tests.helpers.dt.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = now = dt.datetime(2022, 9, 17, 18, 9)
            builder = ArtifactFactory()

        self.assertEqual(builder.timestamp, int(now.timestamp()))

    def test_advance(self) -> None:
        timer = self.fixtures.builder.timer

        result = self.fixtures.builder.advance(450)

        self.assertEqual(result, timer + 450)
        self.assertEqual(self.fixtures.builder.timer, result)

    def test_build_should_add_to_packages(self) -> None:
        timer = self.fixtures.builder.timer
        build = BuildFactory()
        package = self.fixtures.builder.build(
            build, "app-vim/gentoo-syntax-1", repo="marduk", build_id=35
        )

        expected = Package(
            cpv="app-vim/gentoo-syntax-1",
            repo="marduk",
            path="app-vim/gentoo-syntax/gentoo-syntax-1-35.gpkg.tar",
            build_id=35,
            size=529,
            build_time=timer + 10,
            build=build,
        )
        self.assertEqual(package, expected)
        build_info = self.fixtures.builder.build_info(build)
        added = [i[0] for i in build_info.package_info if i[1] is PackageStatus.ADDED]
        self.assertEqual(added, [expected])

    def test_remove_should_remove_package(self) -> None:
        build = BuildFactory()
        builder = ArtifactFactory()
        package = builder.get_packages_for_build(build)[0]

        builder.remove(build, package)

        self.assertFalse(package in builder.get_packages_for_build(build))

    def test_get_artifact(self) -> None:
        build = BuildFactory()
        self.fixtures.builder.build(build, "app-vim/gentoo-syntax-1")

        artifact = self.fixtures.builder.get_artifact(build)

        with tarfile.TarFile.open(
            "build.tar.gz", mode="r", fileobj=artifact
        ) as tar_file:
            artifact_contents = [i.path for i in tar_file.getmembers()]

        for item in Content:
            self.assertTrue(item.value in artifact_contents)

        self.assertTrue("binpkgs/Packages" in artifact_contents)

    def test_downloading_artifact_should_advance_timestamp(self) -> None:
        build = BuildFactory()
        builder = ArtifactFactory(timestamp=0)
        self.assertEqual(builder.timestamp, 0)

        builder.get_artifact(build)

        timestamp = builder.timestamp
        self.assertNotEqual(timestamp, 0)

        builder.get_artifact(build)
        self.assertGreater(builder.timestamp, timestamp)

    def test_build_info_with_new_build(self) -> None:
        build = BuildFactory()
        build_info = self.fixtures.builder.build_info(build)

        expected = BuildInfo(
            build_time=self.fixtures.builder.timer * 1000, package_info=[]
        )
        self.assertEqual(expected, build_info)

    def test_build_info_with_existing_build(self) -> None:
        build = BuildFactory()
        self.fixtures.builder.build(build, "app-vim/gentoo-syntax-1")
        build_info = self.fixtures.builder.build_info(build)

        expected = BuildInfo(
            build_time=(self.fixtures.builder.timer - 10) * 1000,
            package_info=[
                (
                    Package(
                        cpv="app-vim/gentoo-syntax-1",
                        repo="gentoo",
                        path="app-vim/gentoo-syntax/gentoo-syntax-1-1.gpkg.tar",
                        build_id=1,
                        size=529,
                        build_time=self.fixtures.builder.timer,
                        build=build,
                    ),
                    PackageStatus.ADDED,
                )
            ],
        )
        self.assertEqual(expected, build_info)

    def test_get_packages_for_build(self) -> None:
        builder = ArtifactFactory()

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


class TreeTestCase(TestCase):
    """Tests for the Tree class"""

    def test_emptytree(self) -> None:
        """Get it? Emptyree :-)"""
        root = Tree()

        self.assertEqual(root.nodes, {})
        self.assertEqual(root.value, None)

    def test_get(self) -> None:
        #
        #              o
        #         _____|____
        #         |        |
        #         A        B
        #              ____|____
        #              |       |
        #              C       D
        #
        root = Tree()
        root.nodes["A"] = Tree("A")
        b_node = root.nodes["B"] = Tree("B")
        b_node.nodes["C"] = Tree("C")
        b_node.nodes["D"] = Tree("D")

        self.assertEqual(root.get(["A"]), "A")
        self.assertEqual(root.get(["B"]), "B")
        self.assertEqual(root.get(["B", "D"]), "D")
        self.assertEqual(b_node.get(["C"]), "C")

        with self.assertRaises(KeyError):
            root.get(["B", "C", "D"])

    def test_set(self) -> None:
        root = Tree()
        root.set(["A"], "A")
        root.set(["B"], "B")
        root.set(["B", "C"], "C")
        root.set(["B", "D"], "D")

        self.assertEqual(root.get(["A"]), "A")
        self.assertEqual(root.get(["B"]), "B")
        self.assertEqual(root.get(["B", "D"]), "D")

        with self.assertRaises(KeyError):
            root.get(["B", "C", "D"])


class MockJenkinsSessionTestCase(TestCase):
    def test_head(self) -> None:
        session = MockJenkinsSession()
        session.root.set(["Test"], "test")

        response = session.head("http://jenkins.invalid/job/Test")

        self.assertEqual(response.status_code, 200)

    def test_head_404(self) -> None:
        session = MockJenkinsSession()

        response = session.head("http://jenkins.invalid/job/Test")

        self.assertEqual(response.status_code, 404)

    def test_post(self) -> None:
        session = MockJenkinsSession()

        response = session.post(
            "http://jenkins.invalid/createItem", data=b"test", params={"name": "Test"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.root.get(["Test"]), b"test")

    def test_post_404(self) -> None:
        session = MockJenkinsSession()

        response = session.post(
            "http://jenkins.invalid/job/Gentoo/createItem",
            data=b"test",
            params={"name": "Test"},
        )

        self.assertEqual(response.status_code, 404)

        with self.assertRaises(KeyError):
            session.root.get(["Gentoo", "Test"])

    def test_post_without_createitem(self) -> None:
        session = MockJenkinsSession()

        response = session.post(
            "http://jenkins.invalid/Test", data=b"test", params={"name": "Test"}
        )

        self.assertEqual(response.status_code, 400)

    def test_get(self) -> None:
        session = MockJenkinsSession()
        session.root.set(["Test"], "<jenkins>test</jenkins>")

        response = session.get("http://jenkins.invalid/job/Test/config.xml")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"<jenkins>test</jenkins>")
        self.assertEqual(response.text, "<jenkins>test</jenkins>")

    def test_get_without_configxml(self) -> None:
        """I don't think this happens in real life, but for testing..."""
        session = MockJenkinsSession()
        session.root.set(["Test"], "<jenkins>test</jenkins>")

        response = session.get("http://jenkins.invalid/job/Test/")

        self.assertEqual(response.status_code, 400)

    def test_get_404(self) -> None:
        session = MockJenkinsSession()

        response = session.get("http://jenkins.invalid/job/Test/config.xml")

        self.assertEqual(response.status_code, 404)
