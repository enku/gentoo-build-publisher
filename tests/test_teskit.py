"""I heard you like tests..."""

# pylint: disable=missing-docstring,unused-argument
import datetime as dt
import sys
import tarfile
from unittest import TestCase, mock
from zoneinfo import ZoneInfo

from unittest_fixtures import Fixtures, fixture, given, where

import gbp_testkit.fixtures as testkit
from gbp_testkit.factories import (
    ArtifactFactory,
    BuildFactory,
    BuildInfo,
    CICDPackage,
    PackageStatus,
)
from gbp_testkit.helpers import MockJenkinsSession, Tree, ts
from gentoo_build_publisher.types import Content


@fixture()
def builder_fixture(_fixtures: Fixtures) -> ArtifactFactory:
    return ArtifactFactory(initial_packages=[])


@fixture()
def mock_jenkins_session(_: Fixtures) -> MockJenkinsSession:
    return MockJenkinsSession()


@given(builder_fixture)
class ArtifactFactoryTestCase(TestCase):
    def test_timestamp(self, fixtures: Fixtures) -> None:
        with mock.patch("gbp_testkit.helpers.dt.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = now = dt.datetime(2022, 9, 17, 18, 9)
            builder = ArtifactFactory()

        self.assertEqual(builder.timestamp, int(now.timestamp()))

    def test_advance(self, fixtures: Fixtures) -> None:
        timer = fixtures.builder.timer

        result = fixtures.builder.advance(450)

        self.assertEqual(result, timer + 450)
        self.assertEqual(fixtures.builder.timer, result)

    def test_build_should_add_to_packages(self, fixtures: Fixtures) -> None:
        timer = fixtures.builder.timer
        build = BuildFactory()
        package = fixtures.builder.build(
            build, "app-vim/gentoo-syntax-1", repo="marduk", build_id=35
        )

        expected = CICDPackage(
            cpv="app-vim/gentoo-syntax-1",
            repo="marduk",
            path="app-vim/gentoo-syntax/gentoo-syntax-1-35.gpkg.tar",
            build_id=35,
            size=529,
            slot=0,
            build_time=timer + 10,
        )
        self.assertEqual(package, expected)
        build_info = fixtures.builder.build_info(build)
        added = [i[0] for i in build_info.package_info if i[1] is PackageStatus.ADDED]
        self.assertEqual(added, [expected])

    def test_build_on_same_package_bumps_buildid(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        fixtures.builder.build(
            build, "app-vim/gentoo-syntax-1", repo="marduk", build_id=35
        )
        build = BuildFactory()
        package = fixtures.builder.build(
            build, "app-vim/gentoo-syntax-1", repo="marduk"
        )
        self.assertEqual(package.build_id, 36)

    def test_build_on_same_package_and_slot_removes_previous(
        self, fixtures: Fixtures
    ) -> None:
        builder: ArtifactFactory = fixtures.builder
        build1 = BuildFactory()
        builder.build(build1, "app-vim/gentoo-syntax-1")
        build2 = BuildFactory()
        builder.build(build2, "app-vim/gentoo-syntax-2")

        packages = builder.get_packages_for_build(build2)

        self.assertEqual(len(packages), 1)
        package = packages[0]
        self.assertEqual(
            (package.cpv, package.build_id), ("app-vim/gentoo-syntax-2", 1)
        )

        build3 = BuildFactory()
        builder.build(build3, "app-vim/gentoo-syntax-3", slot=3)
        packages = builder.get_packages_for_build(build3)

        self.assertEqual(len(packages), 2)
        self.assertEqual(
            [(p.cpv, p.build_id) for p in packages],
            [("app-vim/gentoo-syntax-2", 1), ("app-vim/gentoo-syntax-3", 1)],
        )

    def test_remove_should_remove_package(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        builder = ArtifactFactory()
        package = builder.get_packages_for_build(build)[0]

        builder.remove(build, package)

        self.assertFalse(package in builder.get_packages_for_build(build))

    def test_get_artifact(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        fixtures.builder.build(build, "app-vim/gentoo-syntax-1")

        artifact = fixtures.builder.get_artifact(build)

        with tarfile.TarFile.open(
            "build.tar.gz", mode="r", fileobj=artifact
        ) as tar_file:
            artifact_contents = [i.path for i in tar_file.getmembers()]

        for item in Content:
            self.assertTrue(item.value in artifact_contents)

        self.assertTrue("binpkgs/Packages" in artifact_contents)

    def test_downloading_artifact_should_advance_timestamp(
        self, fixtures: Fixtures
    ) -> None:
        build = BuildFactory()
        builder = ArtifactFactory(timestamp=0)
        self.assertEqual(builder.timestamp, 0)

        builder.get_artifact(build)

        timestamp = builder.timestamp
        self.assertNotEqual(timestamp, 0)

        builder.get_artifact(build)
        self.assertGreater(builder.timestamp, timestamp)

    def test_build_info_with_new_build(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        build_info = fixtures.builder.build_info(build)

        expected = BuildInfo(build_time=fixtures.builder.timer * 1000, package_info=[])
        self.assertEqual(expected, build_info)

    def test_build_info_with_existing_build(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        fixtures.builder.build(build, "app-vim/gentoo-syntax-1")
        build_info = fixtures.builder.build_info(build)

        expected = BuildInfo(
            build_time=(fixtures.builder.timer - 10) * 1000,
            package_info=[
                (
                    CICDPackage(
                        cpv="app-vim/gentoo-syntax-1",
                        repo="gentoo",
                        path="app-vim/gentoo-syntax/gentoo-syntax-1-1.gpkg.tar",
                        build_id=1,
                        size=529,
                        slot=0,
                        build_time=fixtures.builder.timer,
                    ),
                    PackageStatus.ADDED,
                )
            ],
        )
        self.assertEqual(expected, build_info)

    def test_get_packages_for_build(self, fixtures: Fixtures) -> None:
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


@given(mock_jenkins_session)
class MockJenkinsSessionTestCase(TestCase):
    def test_head(self, fixtures: Fixtures) -> None:
        session = fixtures.mock_jenkins_session
        session.root.set(["Test"], "test")

        response = session.head("http://jenkins.invalid/job/Test")

        self.assertEqual(response.status_code, 200)

    def test_head_404(self, fixtures: Fixtures) -> None:
        session = fixtures.mock_jenkins_session

        response = session.head("http://jenkins.invalid/job/Test")

        self.assertEqual(response.status_code, 404)

    def test_post(self, fixtures: Fixtures) -> None:
        session = fixtures.mock_jenkins_session

        response = session.post(
            "http://jenkins.invalid/createItem", data=b"test", params={"name": "Test"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.root.get(["Test"]), b"test")

    def test_post_404(self, fixtures: Fixtures) -> None:
        session = fixtures.mock_jenkins_session

        response = session.post(
            "http://jenkins.invalid/job/Gentoo/createItem",
            data=b"test",
            params={"name": "Test"},
        )

        self.assertEqual(response.status_code, 404)

        with self.assertRaises(KeyError):
            session.root.get(["Gentoo", "Test"])

    def test_post_without_createitem(self, fixtures: Fixtures) -> None:
        session = fixtures.mock_jenkins_session

        response = session.post(
            "http://jenkins.invalid/Test", data=b"test", params={"name": "Test"}
        )

        self.assertEqual(response.status_code, 400)

    def test_get(self, fixtures: Fixtures) -> None:
        session = fixtures.mock_jenkins_session
        session.root.set(["Test"], "<jenkins>test</jenkins>")

        response = session.get("http://jenkins.invalid/job/Test/config.xml")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"<jenkins>test</jenkins>")
        self.assertEqual(response.text, "<jenkins>test</jenkins>")

    def test_get_without_configxml(self, fixtures: Fixtures) -> None:
        """I don't think this happens in real life, but for testing..."""
        session = fixtures.mock_jenkins_session
        session.root.set(["Test"], "<jenkins>test</jenkins>")

        response = session.get("http://jenkins.invalid/job/Test/")

        self.assertEqual(response.status_code, 400)

    def test_get_404(self, fixtures: Fixtures) -> None:
        session = fixtures.mock_jenkins_session

        response = session.get("http://jenkins.invalid/job/Test/config.xml")

        self.assertEqual(response.status_code, 404)


@given(foo=testkit.patch)
@where(foo__bar="baz")
@given(version=testkit.patch)
@where(version__target="sys.version", version__new="test")
@given(argv=testkit.patch)
@where(argv__object=sys, argv__target="argv", argv__new=["foo", "bar"])
class PatchTests(TestCase):
    def test_with_no_object_and_no_target(self, fixtures: Fixtures) -> None:
        # Just produces a bare mock
        self.assertIsInstance(fixtures.foo, mock.Mock)

    def test_with_no_object_and_target(self, fixtures: Fixtures) -> None:
        self.assertEqual(sys.version, "test")
        self.assertEqual(fixtures.version, "test")

    def test_with_object_and_target(self, fixtures: Fixtures) -> None:
        self.assertEqual(sys.argv, ["foo", "bar"])
        self.assertEqual(fixtures.argv, ["foo", "bar"])

    def test_attributes(self, fixtures: Fixtures) -> None:
        self.assertEqual(fixtures.foo.bar, "baz")


class TSTests(TestCase):
    def test_without_timezone(self) -> None:
        timestamp = ts("2026-01-21 20:05:55")

        self.assertEqual(timestamp, dt.datetime(2026, 1, 21, 20, 5, 55, tzinfo=dt.UTC))

    def test_with_timezone(self) -> None:
        ct = ZoneInfo("America/Chicago")
        timestamp = ts("2026-01-21 20:05:55", ct)

        self.assertEqual(timestamp, dt.datetime(2026, 1, 21, 20, 5, 55, tzinfo=ct))
