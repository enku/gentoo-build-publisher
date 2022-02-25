"""I heard you like tests..."""
# pylint: disable=missing-docstring
import tarfile
from unittest import TestCase, mock

from gentoo_build_publisher.types import Content, Package

from . import ArtifactBuilder


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
        package = self.builder.build(
            "app-vim/gentoo-syntax", repo="marduk", build_id=35
        )

        expected = Package(
            "app-vim/gentoo-syntax",
            "marduk",
            "app-vim/gentoo/gentoo-syntax-35.xpak",
            35,
            441,
            timer + 10,
        )
        self.assertEqual(package, expected)
        self.assertEqual(self.builder.packages, [package])

    def test_remove_should_remove_package(self):
        builder = ArtifactBuilder()
        package = builder.packages[0]
        self.assertTrue(package in builder.packages)

        builder.remove(package)

        self.assertFalse(package in builder.packages)

    def test_get_artifact(self):
        self.builder.build("app-vim/gentoo-syntax")

        artifact = self.builder.get_artifact()

        with tarfile.TarFile.open(
            "build.tar.gz", mode="r", fileobj=artifact
        ) as tar_file:
            artifact_contents = [i.path for i in tar_file.getmembers()]

        for item in Content:
            self.assertTrue(item.value in artifact_contents)

        self.assertTrue("binpkgs/Packages" in artifact_contents)
        self.assertTrue("binpkgs/gbp.json" in artifact_contents)
