"""I heard you like tests..."""
# pylint: disable=missing-docstring
import datetime as dt
import tarfile
from unittest import TestCase, mock

from gentoo_build_publisher.types import Content, Package

from . import MockJenkinsSession, Tree
from .factories import ArtifactFactory, BuildFactory, BuildInfo, PackageStatus


class ArtifactFactoryTestCase(TestCase):
    def setUp(self):
        super().setUp()

        self.builder = ArtifactFactory(initial_packages=[])

    def test_timestamp(self):
        with mock.patch("tests.dt.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = now = dt.datetime(2022, 9, 17, 18, 9)
            builder = ArtifactFactory()

        self.assertEqual(builder.timestamp, int(now.timestamp()))

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
        builder = ArtifactFactory()
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
        builder = ArtifactFactory(timestamp=0)
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

    def test_emptytree(self):
        """Get it? Emptyree :-)"""
        root = Tree()

        self.assertEqual(root.nodes, {})
        self.assertEqual(root.value, None)

    def test_get(self):
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

    def test_set(self):
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
    def test_head(self):
        session = MockJenkinsSession()
        session.root.set(["Test"], "test")

        response = session.head("http://jenkins.invalid/job/Test")

        self.assertEqual(response.status_code, 200)

    def test_head_404(self):
        session = MockJenkinsSession()

        response = session.head("http://jenkins.invalid/job/Test")

        self.assertEqual(response.status_code, 404)

    def test_post(self):
        session = MockJenkinsSession()

        response = session.post(
            "http://jenkins.invalid/createItem", data=b"test", params={"name": "Test"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.root.get(["Test"]), b"test")

    def test_post_404(self):
        session = MockJenkinsSession()

        response = session.post(
            "http://jenkins.invalid/job/Gentoo/createItem",
            data=b"test",
            params={"name": "Test"},
        )

        self.assertEqual(response.status_code, 404)

        with self.assertRaises(KeyError):
            session.root.get(["Gentoo", "Test"])

    def test_post_without_createitem(self):
        session = MockJenkinsSession()

        response = session.post(
            "http://jenkins.invalid/Test", data=b"test", params={"name": "Test"}
        )

        self.assertEqual(response.status_code, 400)

    def test_get(self):
        session = MockJenkinsSession()
        session.root.set(["Test"], "<jenkins>test</jenkins>")

        response = session.get("http://jenkins.invalid/job/Test/config.xml")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"<jenkins>test</jenkins>")
        self.assertEqual(response.text, "<jenkins>test</jenkins>")

    def test_get_without_configxml(self):
        """I don't think this happens in real life, but for testing..."""
        session = MockJenkinsSession()
        session.root.set(["Test"], "<jenkins>test</jenkins>")

        response = session.get("http://jenkins.invalid/job/Test/")

        self.assertEqual(response.status_code, 400)

    def test_get_404(self):
        session = MockJenkinsSession()

        response = session.get("http://jenkins.invalid/job/Test/config.xml")

        self.assertEqual(response.status_code, 404)
