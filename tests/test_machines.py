"""Tests for the machines module"""

# pylint: disable=missing-docstring
from unittest_fixtures import Fixtures, fixture, given, where

import gbp_testkit.fixtures as testkit
from gbp_testkit import TestCase
from gbp_testkit.factories import BuildFactory
from gentoo_build_publisher import publisher
from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.types import Build


# pylint: disable=unused-argument
@given(testkit.publisher, build1=testkit.build, build2=testkit.build)
@where(build1__machine="foo", build2__machine="foo")
class MachineInfoTestCase(TestCase):
    """Tests for the MachineInfo thingy"""

    def test(self, fixtures: Fixtures) -> None:
        # Given the "foo" builds, one of which is published
        first_build = fixtures.build1
        publisher.publish(first_build)
        latest_build = fixtures.build2
        publisher.pull(latest_build)

        # Given the "other" builds
        for build in BuildFactory.create_batch(3, machine="other"):
            publisher.pull(build)

        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.machine, "foo")
        self.assertEqual(machine_info.build_count, 2)
        self.assertEqual(machine_info.latest_build, publisher.record(latest_build))
        self.assertEqual(machine_info.published_build, first_build)

    def test_empty_db(self, fixtures: Fixtures) -> None:
        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it contains the expected attributes
        self.assertEqual(machine_info.machine, "foo")
        self.assertEqual(machine_info.build_count, 0)
        self.assertEqual(machine_info.latest_build, None)
        self.assertEqual(machine_info.published_build, None)

    def test_builds_property(self, fixtures: Fixtures) -> None:
        # Given the "foo" builds
        builds = BuildFactory.create_batch(3, machine="foo")
        for build in builds:
            publisher.pull(build)

        # Given the MachineInfo for foo
        machine_info = MachineInfo("foo")

        # When we call its .builds method
        result = machine_info.builds

        # Then we get the list of builds in reverse chronological order
        self.assertEqual(result, [publisher.record(i) for i in reversed(builds)])

    def test_tags_property_shows_tags_across_machines_builds(
        self, fixtures: Fixtures
    ) -> None:
        # Given the tagged builds for "foo"
        builds = BuildFactory.create_batch(3, machine="foo")
        for build in builds:
            publisher.pull(build)

        publisher.tag(builds[-1], "testing")
        publisher.tag(builds[0], "stable")

        # When we get MachineInfo for foo
        machine_info = MachineInfo("foo")

        # Then it has the the tags for all builds
        self.assertEqual(machine_info.tags, ["stable", "testing"])


@fixture()
def builds_fixture(_fixtures: Fixtures, count: int = 4) -> list[Build]:
    builds: list[Build] = BuildFactory.create_batch(count)
    return builds


@fixture(testkit.publisher, builds_fixture)
def machine_info_fixture(fixtures: Fixtures) -> MachineInfo:
    machine = fixtures.builds[0].machine

    for build in fixtures.builds:
        MachineInfoLegacyBuiltTestCase.pull_build_with_no_built_timestamp(build)

    publisher.publish(fixtures.builds[2])

    assert not any(
        build.built for build in publisher.repo.build_records.for_machine(machine)
    )

    return MachineInfo(fixtures.builds[0].machine)


@given(builds_fixture, testkit.publisher, machine_info_fixture)
class MachineInfoLegacyBuiltTestCase(TestCase):
    """Test case for MachineInfo where built field is not always populated"""

    @staticmethod
    def pull_build_with_no_built_timestamp(build: Build) -> None:
        publisher.pull(build)
        publisher.repo.build_records.save(publisher.record(build), built=None)

    def test_build_count(self, fixtures: Fixtures) -> None:
        self.assertEqual(fixtures.machine_info.build_count, 4)

    def test_builds(self, fixtures: Fixtures) -> None:
        builds = fixtures.machine_info.builds

        expected = list(reversed([publisher.record(i) for i in fixtures.builds]))
        self.assertEqual(expected, builds)

    def test_latest_build(self, fixtures: Fixtures) -> None:
        build4 = fixtures.builds[3]
        latest_build = fixtures.machine_info.latest_build

        self.assertEqual(publisher.record(build4), latest_build)

    def test_latest_with_latest_having_built_timestamp(
        self, fixtures: Fixtures
    ) -> None:
        build5 = BuildFactory()
        publisher.pull(build5)

        latest_build = fixtures.machine_info.latest_build

        self.assertEqual(publisher.record(build5), latest_build)

    def test_published_build(self, fixtures: Fixtures) -> None:
        build3 = fixtures.builds[2]
        published_build = fixtures.machine_info.published_build

        self.assertEqual(build3, published_build)
        self.assertTrue(publisher.published(build3))
