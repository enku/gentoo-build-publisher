"""Tests for gbp_testkit.factories"""

# pylint: disable=missing-docstring

import tarfile
from unittest import TestCase

from unittest_fixtures import Fixtures, given

from gbp_testkit import factories


@given(build=lambda _: factories.BuildFactory())
class ArtifactFactoryGetArtifactTests(TestCase):
    def test_includes_profile(self, fixtures: Fixtures) -> None:
        # given the build and ArtifactFactory
        build = fixtures.build
        builder = factories.ArtifactFactory()

        # when we acquire the build artifacts
        io = builder.get_artifact(build)

        # then the result contains the /etc/portage/make.profile
        with tarfile.TarFile.open(fileobj=io) as artifact:
            members = artifact.getnames()
            self.assertIn("etc-portage/make.profile", members)

            member = artifact.getmember("etc-portage/make.profile")
            self.assertEqual(member.type, tarfile.SYMTYPE)
            self.assertEqual(
                member.linkname,
                "../../var/db/repos/gentoo/profiles/default/linux/amd64/23.0",
            )

    def test_includes_aux(self, fixtures: Fixtures) -> None:
        # given the build and ArtifactFactory
        build = fixtures.build
        builder = factories.ArtifactFactory()

        # when we acquire the build artifacts with aux files
        io = builder.get_artifact(build, aux={"test.txt": b"this is a test"})

        # then the result contains the the file
        with tarfile.TarFile.open(fileobj=io) as artifact:
            members = artifact.getnames()
            self.assertIn("aux/test.txt", members)

            member = artifact.extractfile("aux/test.txt")
            assert member
            self.assertEqual(member.read(), b"this is a test")
