"""Tests for the jenkins.xml utils"""

# pylint: disable=missing-class-docstring,missing-function-docstring
from unittest import TestCase

from gentoo_build_publisher.jenkins import xml
from gentoo_build_publisher.types import EbuildRepo, MachineJob, Repo


class JenkinsXMLTestCase(TestCase):
    """Tests for the jenkins.xml utils"""

    def test_xml_build_machine(self) -> None:
        job = MachineJob(
            name="test",
            repo=Repo(url="https://github.com/enku/gbp-machines.git", branch="feature"),
            ebuild_repos=["gentoo", "marduk"],
        )

        xml_str = xml.build_machine(job)

        self.assertRegex(
            xml_str, r"<upstreamProjects>repos/gentoo,repos/marduk</upstreamProjects>"
        )
        self.assertRegex(
            xml_str, r"<url>https://github\.com/enku/gbp-machines\.git</url>"
        )
        self.assertRegex(xml_str, r"<name>\*/feature</name>")

    def test_xml_build_repo(self) -> None:
        repo = EbuildRepo(
            url="https://anongit.gentoo.org/git/repo/gentoo.git",
            branch="feature",
            name="test",
        )

        xml_str = xml.build_repo(repo)

        self.assertRegex(xml_str, r"<name>\*/feature</name>")
        self.assertRegex(
            xml_str, r"<url>https://anongit\.gentoo\.org/git/repo/gentoo\.git</url>"
        )
