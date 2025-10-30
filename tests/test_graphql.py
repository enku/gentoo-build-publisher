"""Tests for the GraphQL interface for Gentoo Build Publisher"""

# pylint: disable=missing-docstring,too-many-lines,unused-argument
import datetime as dt
from typing import Any

from unittest_fixtures import Fixtures, fixture, given, params, where

import gbp_testkit.fixtures as testkit
from gbp_testkit import TestCase
from gbp_testkit.factories import (
    PACKAGE_INDEX,
    BuildFactory,
    BuildRecordFactory,
    package_factory,
)
from gbp_testkit.helpers import BUILD_LOGS, graphql
from gentoo_build_publisher import plugins, publisher
from gentoo_build_publisher.cache import clear as cache_clear
from gentoo_build_publisher.graphql import scalars
from gentoo_build_publisher.jenkins import ProjectPath
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import Build, Content, EbuildRepo, MachineJob, Repo
from gentoo_build_publisher.utils import get_version, time
from gentoo_build_publisher.worker import tasks

SEARCH_PARAMS = {"enum": ("NOTES", "LOGS"), "field": ("note", "logs")}
WORKER = "gentoo_build_publisher.graphql.mutations.worker"
DATE = dt.date(2025, 10, 8)
TIMESTAMP = dt.datetime(
    2025, 7, 14, 15, 45, 30, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))
)


def assert_data(
    test_case: TestCase, result: dict[str, Any], expected: dict[str, Any]
) -> None:
    test_case.assertFalse(result.get("errors"))

    data = result["data"]

    test_case.assertEqual(data, expected)


@given(testkit.tmpdir, testkit.publisher, testkit.client, utctime=testkit.patch)
@where(utctime__target="gentoo_build_publisher.build_publisher.utctime")
@where(utctime__return_value=time.utctime(dt.datetime(2022, 3, 1, 6, 28, 44)))
class BuildQueryTestCase(TestCase):
    """Tests for the build query"""

    maxDiff = None

    def test(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        artifact_builder = publisher.jenkins.artifact_builder
        artifact_builder.timer = 1646115094
        artifact_builder.build(build, "x11-wm/mutter-41.3")
        artifact_builder.build(build, "acct-group/sgx-0", repo="marduk")

        publisher.pull(build)
        publisher.tag(build, "prod")

        query = """
        query ($id: ID!) {
          build(id: $id) {
            id
            machine
            pulled
            built
            submitted
            published
            tags
            logs
            packagesBuilt {
              cpv
              path
              buildId
              url
            }
          }
        }
        """

        result = graphql(fixtures.client, query, variables={"id": build.id})

        expected = {
            "build": {
                "id": build.id,
                "machine": build.machine,
                "pulled": True,
                "published": False,
                "tags": ["prod"],
                "logs": BUILD_LOGS,
                "built": "2022-03-01T06:28:44+00:00",
                "submitted": "2022-03-01T06:28:44+00:00",
                "packagesBuilt": [
                    # pylint: disable=line-too-long
                    {
                        "cpv": "acct-group/sgx-0",
                        "path": "acct-group/sgx/sgx-0-1.gpkg.tar",
                        "buildId": "1",
                        "url": f"/machines/{build.machine}/builds/{build.build_id}/packages/acct-group/sgx/sgx-0-1",
                    },
                    {
                        "cpv": "x11-wm/mutter-41.3",
                        "path": "x11-wm/mutter/mutter-41.3-1.gpkg.tar",
                        "buildId": "1",
                        "url": f"/machines/{build.machine}/builds/{build.build_id}/packages/x11-wm/mutter/mutter-41.3-1",
                    },
                ],
            }
        }

        assert_data(self, result, expected)

    def test_packages(self, fixtures: Fixtures) -> None:
        # given the pulled build with packages
        build = BuildFactory()
        publisher.pull(build)

        # when we query the build's packages
        query = """
        query ($id: ID!) {
          build(id: $id) {
            packages
          }
        }
        """
        result = graphql(fixtures.client, query, {"id": build.id})

        # Then we get the list of packages in the build
        assert_data(self, result, {"build": {"packages": PACKAGE_INDEX}})

    def test_packages_build_id(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)

        # when we query the build's packages
        query = """
        query ($id: ID!) {
          build(id: $id) {
            packages(buildId: true)
          }
        }
        """
        result = graphql(fixtures.client, query, {"id": build.id})

        # Then we get the list of packages in the build
        expected = [f"{p}-1" for p in PACKAGE_INDEX]
        assert_data(self, result, {"build": {"packages": expected}})

    def test_packages_when_not_pulled_returns_none(self, fixtures: Fixtures) -> None:
        # given the unpulled package
        build = BuildFactory()
        publisher.repo.build_records.save(publisher.record(build))

        # when we query the build's packages
        query = """
        query ($id: ID!) {
          build(id: $id) {
            packages
          }
        }
        """
        result = graphql(fixtures.client, query, {"id": build.id})

        # Then none is returned
        assert_data(self, result, {"build": {"packages": None}})

    def test_packages_should_return_none_when_package_index_missing(
        self, fixtures: Fixtures
    ) -> None:
        # given the pulled build with index file missing
        build = BuildFactory()
        publisher.pull(build)

        (publisher.storage.get_path(build, Content.BINPKGS) / "Packages").unlink()

        # when we query the build's packages
        query = """
        query ($id: ID!) {
          build(id: $id) {
            packages
          }
        }
        """
        result = graphql(fixtures.client, query, {"id": build.id})

        # Then none is returned
        assert_data(self, result, {"build": {"packages": None}})

    def test_package_detail(self, fixtures: Fixtures) -> None:
        client = fixtures.client
        build = BuildFactory()
        publisher.pull(build)

        query = """
        query ($id: ID!) {
          build(id: $id) {
            packageDetail {
               cpv
               size
               path
            }
          }
        }
        """
        result = graphql(client, query, {"id": build.id})
        expected = [
            {
                "cpv": "acct-group/sgx-0",
                "path": "acct-group/sgx/sgx-0-1.gpkg.tar",
                "size": 256,
            },
            {
                "cpv": "app-admin/perl-cleaner-2.30",
                "path": "app-admin/perl-cleaner/perl-cleaner-2.30-1.gpkg.tar",
                "size": 729,
            },
            {
                "cpv": "app-arch/unzip-6.0_p26",
                "path": "app-arch/unzip/unzip-6.0_p26-1.gpkg.tar",
                "size": 484,
            },
            {
                "cpv": "app-crypt/gpgme-1.14.0",
                "path": "app-crypt/gpgme/gpgme-1.14.0-1.gpkg.tar",
                "size": 484,
            },
        ]
        assert_data(self, result, {"build": {"packageDetail": expected}})


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class BuildsQueryTestCase(TestCase):
    """Tests for the builds query"""

    maxDiff = None

    def test(self, fixtures: Fixtures) -> None:
        now = dt.datetime(2021, 9, 30, 20, 17, tzinfo=dt.UTC)
        builds = BuildFactory.create_batch(3)

        for build in builds:
            record = publisher.record(build)
            publisher.repo.build_records.save(record, completed=now)

        builds.sort(key=lambda build: build.build_id, reverse=True)
        query = """
        query ($machine: String!) {
          builds(machine: $machine) {
            id
            completed
          }
        }
        """

        result = graphql(
            fixtures.client, query, variables={"machine": builds[0].machine}
        )

        expected = [
            {"id": build.id, "completed": "2021-09-30T20:17:00+00:00"}
            for build in builds
        ]

        assert_data(self, result, {"builds": expected})

    def test_older_build_pulled_after_newer_should_not_sort_before(
        self, fixtures: Fixtures
    ) -> None:
        # Build first build
        first_build = BuildFactory(machine="lighthouse", build_id="10000")
        publisher.jenkins.artifact_builder.build_info(first_build)

        # Wait one hour
        publisher.jenkins.artifact_builder.advance(3600)

        # Build second build
        second_build = BuildFactory(machine="lighthouse", build_id="10001")
        publisher.jenkins.artifact_builder.build_info(second_build)

        # Pull second build
        publisher.pull(second_build)

        # Pull first build
        publisher.pull(first_build)

        # Query the machine's builds
        query = """
        query ($machine: String!) {
          builds(machine: $machine) {
            id
          }
        }
        """
        result = graphql(fixtures.client, query, variables={"machine": "lighthouse"})

        assert_data(
            self,
            result,
            {"builds": [{"id": "lighthouse.10001"}, {"id": "lighthouse.10000"}]},
        )


@fixture(testkit.publisher)
def latest(_fixtures: Fixtures) -> Build:
    publisher.repo.build_records.save(
        BuildRecordFactory.build(
            built=dt.datetime(2021, 4, 25, 18, 0, tzinfo=dt.UTC),
            submitted=dt.datetime(2021, 4, 25, 18, 10, tzinfo=dt.UTC),
            completed=dt.datetime(2021, 4, 28, 17, 13, tzinfo=dt.UTC),
        )
    )
    latest_build: Build
    publisher.repo.build_records.save(
        latest_build := BuildRecordFactory.build(
            built=dt.datetime(2022, 2, 25, 12, 8, tzinfo=dt.UTC),
            submitted=dt.datetime(2022, 2, 25, 0, 15, tzinfo=dt.UTC),
            completed=dt.datetime(2022, 2, 25, 0, 20, tzinfo=dt.UTC),
        )
    )
    publisher.repo.build_records.save(
        BuildRecordFactory.build(
            submitted=dt.datetime(2022, 2, 25, 6, 50, tzinfo=dt.UTC)
        )
    )
    return latest_build


@given(testkit.tmpdir, testkit.publisher, latest, testkit.client)
class LatestQueryTestCase(TestCase):
    """Tests for the latest query"""

    def test_when_no_builds_should_respond_with_none(self, fixtures: Fixtures) -> None:
        query = """
        {
          latest(machine: "bogus") {
            id
          }
        }
        """
        result = graphql(fixtures.client, query)

        assert_data(self, result, {"latest": None})

    def test_should_return_the_latest_submitted_completed(
        self, fixtures: Fixtures
    ) -> None:
        query = """
        {
          latest(machine: "babette") {
            id
          }
        }
        """
        result = graphql(fixtures.client, query)

        assert_data(self, result, {"latest": {"id": str(fixtures.latest)}})


@fixture(testkit.publisher)
def diff_query_builds(fixtures: Fixtures) -> dict[str, Build]:
    # Given the first build with tar-1.34
    left = BuildFactory()
    artifact_builder = publisher.jenkins.artifact_builder
    old = artifact_builder.build(left, "app-arch/tar-1.34")
    publisher.pull(left)

    # Given the second build with tar-1.35
    right = BuildFactory()
    artifact_builder.build(right, "app-arch/tar-1.35")
    artifact_builder.remove(right, old)
    publisher.pull(right)

    return {"left": left, "right": right}


@given(testkit.tmpdir, testkit.publisher, diff_query_builds, testkit.client)
class DiffQueryTestCase(TestCase):
    """Tests for the diff query"""

    def test(self, fixtures: Fixtures) -> None:
        # When we call get the diff view given the 2 builds
        query = """
        query Diff($left: ID!, $right: ID!) {
          diff(left: $left, right: $right) {
            left {
              id
            }
            right {
              id
            }
            items {
              item
              status
            }
          }
        }
        """
        builds = fixtures.diff_query_builds
        variables = {"left": builds["left"].id, "right": builds["right"].id}
        result = graphql(fixtures.client, query, variables=variables)

        # Then the differences are given between the two builds
        expected = {
            "diff": {
                "left": {"id": builds["left"].id},
                "right": {"id": builds["right"].id},
                "items": [
                    {"item": "app-arch/tar-1.34-1", "status": "REMOVED"},
                    {"item": "app-arch/tar-1.35-1", "status": "ADDED"},
                ],
            }
        }
        assert_data(self, result, expected)

    def test_should_exclude_build_data_when_not_selected(
        self, fixtures: Fixtures
    ) -> None:
        query = """
        query ($left: ID!, $right: ID!) {
          diff(left: $left, right: $right) {
            items {
              item
              status
            }
          }
        }
        """
        builds = fixtures.diff_query_builds
        variables = {"left": builds["left"].id, "right": builds["right"].id}

        result = graphql(fixtures.client, query, variables=variables)

        # Then the differences are given between the two builds
        expected = {
            "diff": {
                "items": [
                    {"item": "app-arch/tar-1.34-1", "status": "REMOVED"},
                    {"item": "app-arch/tar-1.35-1", "status": "ADDED"},
                ]
            }
        }
        assert_data(self, result, expected)

    def test_should_return_error_when_left_does_not_exist(
        self, fixtures: Fixtures
    ) -> None:
        query = """
        query Diff($left: ID!, $right: ID!) {
          diff(left: $left, right: $right) {
            left {
              id
            }
            right {
              id
            }
            items {
              item
              status
            }
          }
        }
        """
        builds = fixtures.diff_query_builds
        variables = {"left": "bogus.1", "right": builds["right"].id}
        result = graphql(fixtures.client, query, variables=variables)

        # Then an error is returned
        self.assertEqual(result["data"]["diff"], None)
        self.assertEqual(
            result["errors"][0]["message"], "Build does not exist: bogus.1"
        )

    def test_should_return_error_when_right_does_not_exist(
        self, fixtures: Fixtures
    ) -> None:
        query = """
        query ($left: ID!, $right: ID!) {
          diff(left: $left, right: $right) {
            left {
              id
            }
            right {
              id
            }
            items {
              item
              status
            }
          }
        }
        """
        builds = fixtures.diff_query_builds
        variables = {"left": builds["left"].id, "right": "bogus.1"}
        result = graphql(fixtures.client, query, variables=variables)

        # Then an error is returned
        self.assertEqual(result["data"]["diff"], None)
        self.assertEqual(
            result["errors"][0]["message"], "Build does not exist: bogus.1"
        )

    def test_diff_with_package(self, fixtures: Fixtures) -> None:
        query = """
        query Diff($left: ID!, $right: ID!) {
          diff(left: $left, right: $right) {
            items {
              package {
                build { id }
                cpv
                buildId
              }
              status
            }
          }
        }
        """
        left = fixtures.diff_query_builds["left"]
        right = fixtures.diff_query_builds["right"]
        variables = {"left": left.id, "right": right.id}
        result = graphql(fixtures.client, query, variables=variables)

        expected = {
            "diff": {
                "items": [
                    {
                        "package": {
                            "build": {"id": left.id},
                            "cpv": "app-arch/tar-1.34",
                            "buildId": "1",
                        },
                        "status": "REMOVED",
                    },
                    {
                        "package": {
                            "build": {"id": right.id},
                            "cpv": "app-arch/tar-1.35",
                            "buildId": "1",
                        },
                        "status": "ADDED",
                    },
                ]
            }
        }
        assert_data(self, result, expected)


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class MachinesQueryTestCase(TestCase):
    """Tests for the machines query"""

    maxDiff = None

    def test(self, fixtures: Fixtures) -> None:
        babette_builds = BuildFactory.create_batch(3, machine="babette")
        lighthouse_builds = BuildFactory.create_batch(3, machine="lighthouse")
        pf = package_factory()

        for build in babette_builds + lighthouse_builds:
            publisher.jenkins.artifact_builder.build(build, next(pf))
            publisher.pull(build)

        # publish a build
        build = babette_builds[-1]
        publisher.publish(build)

        query = """
        {
          machines {
            machine
            buildCount
            latestBuild {
              id
            }
            publishedBuild {
              id
            }
            builds {
              id
            }
            packageCount
            packagesByDay {
              date
              packages {
                cpv
                build { id }
              }
            }
            totalPackageSize
          }
        }
        """

        result = graphql(fixtures.client, query)

        today = dt.date.today()
        expected = [
            {
                "machine": "babette",
                "buildCount": 3,
                "builds": [{"id": i.id} for i in reversed(babette_builds)],
                "latestBuild": {"id": build.id},
                "publishedBuild": {"id": build.id},
                "packageCount": 18,
                "packagesByDay": [
                    {
                        "date": today.isoformat(),
                        "packages": [
                            {
                                "cpv": "dev-python/markdown-1.0",
                                "build": {"id": str(babette_builds[0])},
                            },
                            {
                                "cpv": "dev-python/mesa-1.0",
                                "build": {"id": str(babette_builds[1])},
                            },
                            {
                                "cpv": "dev-python/pycups-1.0",
                                "build": {"id": str(babette_builds[2])},
                            },
                        ],
                    }
                ],
                "totalPackageSize": "8609",
            },
            {
                "machine": "lighthouse",
                "buildCount": 3,
                "builds": [{"id": i.id} for i in reversed(lighthouse_builds)],
                "latestBuild": {"id": lighthouse_builds[-1].id},
                "publishedBuild": None,
                "packageCount": 18,
                "packagesByDay": [
                    {
                        "date": today.isoformat(),
                        "packages": [
                            {
                                "cpv": "dev-python/ffmpeg-1.0",
                                "build": {"id": str(lighthouse_builds[1])},
                            },
                            {
                                "cpv": "dev-python/gcc-1.0",
                                "build": {"id": str(lighthouse_builds[0])},
                            },
                            {
                                "cpv": "dev-python/xwayland-1.0",
                                "build": {"id": str(lighthouse_builds[2])},
                            },
                        ],
                    }
                ],
                "totalPackageSize": "8242",
            },
        ]
        assert_data(self, result, {"machines": expected})

    def test_only_machine(self, fixtures: Fixtures) -> None:
        # basically test that only selecting the name doesn't query other infos
        # (coverage.py)
        for build in BuildFactory.create_batch(
            2, machine="babette"
        ) + BuildFactory.create_batch(3, machine="lighthouse"):
            publisher.pull(build)

        query = """
        {
          machines {
            machine
          }
        }
        """
        result = graphql(fixtures.client, query)

        assert_data(
            self,
            result,
            {"machines": [{"machine": "babette"}, {"machine": "lighthouse"}]},
        )

    def test_latest_build_is_published(self, fixtures: Fixtures) -> None:
        build = BuildFactory.create()
        publisher.pull(build)

        query = """
        {
            machines {
                machine
                buildCount
                latestBuild {
                    id
                    published
                }
            }
        }
        """
        result = graphql(fixtures.client, query)

        self.assertFalse(result["data"]["machines"][0]["latestBuild"]["published"])

        publisher.publish(build)
        result = graphql(fixtures.client, query)
        self.assertTrue(result["data"]["machines"][0]["latestBuild"]["published"])

    def test_with_names_filter(self, fixtures: Fixtures) -> None:
        builds = [
            *BuildFactory.create_batch(3, machine="foo"),
            *BuildFactory.create_batch(2, machine="bar"),
            *BuildFactory.create_batch(1, machine="baz"),
        ]
        for build in builds:
            publisher.pull(build)

        query = """
        {
          machines(names: ["bar", "baz"]) {
            machine
          }
        }
        """
        result = graphql(fixtures.client, query)

        self.assertEqual(len(result["data"]["machines"]), 2)


@given(testkit.tmpdir, testkit.publisher, testkit.client, worker=testkit.patch)
@where(worker__target=WORKER)
class PublishMutationTestCase(TestCase):
    """Tests for the publish mutation"""

    def test_publish_when_pulled(self, fixtures: Fixtures) -> None:
        """Should publish builds"""
        build = BuildFactory()
        publisher.pull(build)

        query = """
        mutation ($id: ID!) {
          publish(id: $id) {
            publishedBuild {
              id
            }
          }
        }
        """
        result = graphql(fixtures.client, query, variables={"id": build.id})

        assert_data(self, result, {"publish": {"publishedBuild": {"id": build.id}}})

    def test_publish_when_not_pulled(self, fixtures: Fixtures) -> None:
        """Should publish builds"""
        query = """
        mutation {
          publish(id: "babette.193") {
            publishedBuild {
              id
            }
          }
        }
        """
        graphql(fixtures.client, query)

        fixtures.worker.run.assert_called_once_with(tasks.publish_build, "babette.193")


@given(testkit.tmpdir, testkit.publisher, testkit.client, worker=testkit.patch)
@where(worker__target=WORKER)
class PullMutationTestCase(TestCase):
    """Tests for the pull mutation"""

    def test(self, fixtures: Fixtures) -> None:
        """Should publish builds"""
        build = BuildFactory()

        query = """
        mutation ($id: ID!) {
          pull(id: $id) {
            publishedBuild {
              id
            }
          }
        }"""
        result = graphql(fixtures.client, query, variables={"id": build.id})

        assert_data(self, result, {"pull": {"publishedBuild": None}})
        fixtures.worker.run.assert_called_once_with(
            tasks.pull_build, build.id, note=None, tags=None
        )

    def test_pull_with_note(self, fixtures: Fixtures) -> None:
        build = BuildFactory()

        query = """
        mutation ($id: ID!, $note: String) {
          pull(id: $id, note: $note) {
            publishedBuild {
              id
            }
          }
        }"""
        result = graphql(
            fixtures.client, query, variables={"id": build.id, "note": "This is a test"}
        )

        assert_data(self, result, {"pull": {"publishedBuild": None}})
        fixtures.worker.run.assert_called_once_with(
            tasks.pull_build, build.id, note="This is a test", tags=None
        )

    def test_pull_with_tag(self, fixtures: Fixtures) -> None:
        build = BuildFactory()

        query = """
        mutation ($id: ID!, $tags: [String!]) {
          pull(id: $id, tags: $tags) {
            publishedBuild {
              id
            }
          }
        }"""
        result = graphql(
            fixtures.client, query, variables={"id": build.id, "tags": ["emptytree"]}
        )

        assert_data(self, result, {"pull": {"publishedBuild": None}})
        fixtures.worker.run.assert_called_once_with(
            tasks.pull_build, build.id, note=None, tags=["emptytree"]
        )


@given(testkit.tmpdir, testkit.publisher, testkit.client, schedule_build=testkit.patch)
@where(schedule_build__object=publisher)
@where(schedule_build__target="schedule_build")
@where(schedule_build__return_value="https://jenkins.invalid/queue/item/31528/")
class ScheduleBuildMutationTestCase(TestCase):
    """Tests for the build mutation"""

    maxDiff = None

    def test(self, fixtures: Fixtures) -> None:
        query = 'mutation { scheduleBuild(machine: "babette") }'

        result = graphql(fixtures.client, query)

        self.assertEqual(
            result,
            {"data": {"scheduleBuild": "https://jenkins.invalid/queue/item/31528/"}},
        )
        fixtures.schedule_build.assert_called_once_with("babette")

    def test_with_params(self, fixtures: Fixtures) -> None:
        query = """mutation
          {
            scheduleBuild(
              machine: "babette",
              params: [{name: "BUILD_TARGET", value: "world"}],
            )
          }
        """

        result = graphql(fixtures.client, query)

        self.assertEqual(
            result,
            {"data": {"scheduleBuild": "https://jenkins.invalid/queue/item/31528/"}},
        )
        fixtures.schedule_build.assert_called_once_with("babette", BUILD_TARGET="world")

    def test_should_return_error_when_schedule_build_fails(
        self, fixtures: Fixtures
    ) -> None:
        query = 'mutation { scheduleBuild(machine: "babette") }'
        fixtures.schedule_build.side_effect = Exception("The end is near")

        result = graphql(fixtures.client, query)

        expected = {
            "data": {"scheduleBuild": None},
            "errors": [
                {
                    "locations": [{"column": 12, "line": 1}],
                    "message": "The end is near",
                    "path": ["scheduleBuild"],
                }
            ],
        }
        self.assertEqual(result, expected)
        fixtures.schedule_build.assert_called_once_with("babette")

    def test_with_repos(self, fixtures: Fixtures) -> None:
        query = 'mutation { scheduleBuild(machine: "gentoo", isRepo: true) }'

        result = graphql(fixtures.client, query)

        self.assertEqual(
            result,
            {"data": {"scheduleBuild": "https://jenkins.invalid/queue/item/31528/"}},
        )
        fixtures.schedule_build.assert_called_once_with("repos/job/gentoo")


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class KeepBuildMutationTestCase(TestCase):
    """Tests for the keep mutation"""

    maxDiff = None

    def test_should_keep_existing_build(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)
        query = """
        mutation ($id: ID!) {
         keepBuild(id: $id) {
            keep
          }
        }
        """
        result = graphql(fixtures.client, query, variables={"id": str(build)})

        assert_data(self, result, {"keepBuild": {"keep": True}})

    def test_should_return_none_when_build_doesnt_exist(
        self, fixtures: Fixtures
    ) -> None:
        query = """
        mutation KeepBuild($id: ID!) {
         keepBuild(id: $id) {
            keep
          }
        }
        """

        result = graphql(fixtures.client, query, variables={"id": "bogus.309"})

        assert_data(self, result, {"keepBuild": None})


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class ReleaseBuildMutationTestCase(TestCase):
    """Tests for the releaseBuild mutation"""

    def test_should_release_existing_build(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        record = publisher.record(build)
        publisher.repo.build_records.save(record, keep=True)

        query = """
        mutation ($id: ID!) {
         releaseBuild(id: $id) {
            keep
          }
        }
        """

        result = graphql(fixtures.client, query, variables={"id": build.id})

        assert_data(self, result, {"releaseBuild": {"keep": False}})

    def test_should_return_none_when_build_doesnt_exist(
        self, fixtures: Fixtures
    ) -> None:
        query = """
        mutation ($id: ID!) {
         releaseBuild(id: $id) {
            keep
          }
        }
        """

        result = graphql(fixtures.client, query, variables={"id": "bogus.309"})

        assert_data(self, result, {"releaseBuild": None})


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class CreateNoteMutationTestCase(TestCase):
    """Tests for the createNote mutation"""

    def test_set_text(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)
        note_text = "Hello, world!"
        query = """
        mutation ($id: ID!, $note: String) {
         createNote(id: $id, note: $note) {
            notes
          }
        }
        """

        result = graphql(
            fixtures.client, query, variables={"id": str(build), "note": note_text}
        )

        assert_data(self, result, {"createNote": {"notes": note_text}})
        record = publisher.repo.build_records.get(build)
        self.assertEqual(record.note, note_text)

    def test_set_none(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)

        query = """
        mutation ($id: ID!, $note: String) {
         createNote(id: $id, note: $note) {
            notes
          }
        }
        """

        result = graphql(
            fixtures.client, query, variables={"id": build.id, "note": None}
        )

        assert_data(self, result, {"createNote": {"notes": None}})

        record = publisher.record(build)
        self.assertEqual(record.note, None)

    def test_should_return_none_when_build_doesnt_exist(
        self, fixtures: Fixtures
    ) -> None:
        query = """
        mutation ($id: ID!, $note: String) {
         createNote(id: $id, note: $note) {
            notes
          }
        }
        """

        result = graphql(
            fixtures.client, query, variables={"id": "bogus.309", "note": None}
        )

        assert_data(self, result, {"createNote": None})


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class TagsTestCase(TestCase):
    def test_createbuildtag_mutation_tags_the_build(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)
        query = """
        mutation ($id: ID!, $tag: String!) {
         createBuildTag(id: $id, tag: $tag) {
            tags
          }
        }
        """

        result = graphql(
            fixtures.client, query, variables={"id": build.id, "tag": "prod"}
        )

        assert_data(self, result, {"createBuildTag": {"tags": ["prod"]}})

    def test_removebuildtag_mutation_removes_tag_from_the_build(
        self, fixtures: Fixtures
    ) -> None:
        build = BuildFactory()
        publisher.pull(build)
        publisher.tag(build, "prod")

        query = """
        mutation ($machine: String!, $tag: String!) {
         removeBuildTag(machine: $machine, tag: $tag) {
            tags
          }
        }
        """

        result = graphql(
            fixtures.client, query, variables={"machine": build.machine, "tag": "prod"}
        )

        assert_data(self, result, {"removeBuildTag": {"tags": []}})

    def test_resolvetag_query_resolves_tag(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)
        publisher.tag(build, "prod")

        query = """
        query ($machine: String!, $tag: String!) {
         resolveBuildTag(machine: $machine, tag: $tag) {
            id
          }
        }
        """

        result = graphql(
            fixtures.client, query, variables={"machine": build.machine, "tag": "prod"}
        )

        assert_data(self, result, {"resolveBuildTag": {"id": build.id}})

    def test_resolvetag_query_resolves_to_none_when_tag_does_not_exist(
        self, fixtures: Fixtures
    ) -> None:
        build = BuildFactory()
        publisher.pull(build)

        query = """
        query ($machine: String!, $tag: String!) {
         resolveBuildTag(machine: $machine, tag: $tag) {
            id
          }
        }
        """

        result = graphql(
            fixtures.client, query, variables={"machine": build.machine, "tag": "prod"}
        )

        assert_data(self, result, {"resolveBuildTag": None})

    def test_latest_build_tag(self, fixtures: Fixtures) -> None:
        build = BuildFactory()
        publisher.pull(build)

        query = """
        query ($machine: String!, $tag: String!) {
         resolveBuildTag(machine: $machine, tag: $tag) {
            id
          }
        }
        """

        result = graphql(
            fixtures.client, query, variables={"machine": build.machine, "tag": "@"}
        )

        assert_data(self, result, {"resolveBuildTag": {"id": str(build)}})


def search_query_builds(_fixtures: Fixtures) -> list[Build]:
    for field in SEARCH_PARAMS["field"]:
        build1 = BuildFactory()
        record = publisher.record(build1)
        publisher.repo.build_records.save(record, **{field: f"test foo {field}"})
        build2 = BuildFactory()
        record = publisher.record(build2)
        publisher.repo.build_records.save(record, **{field: f"test bar {field}"})

    return [build1, build2]


@given(testkit.tmpdir, testkit.publisher, search_query_builds, testkit.client)
@params(**SEARCH_PARAMS)
class SearchQueryTestCase(TestCase):
    """Tests for the search query"""

    unittest_fixtures_kwarg = "fx"
    query = """
    query ($machine: String!, $field: SearchField!, $key: String!) {
     search(machine: $machine, field: $field, key: $key) {
        logs
        notes
      }
    }
    """

    def test_single_match(self, fx: Fixtures) -> None:
        result = graphql(
            fx.client,
            self.query,
            variables={"machine": "babette", "field": fx.enum, "key": "foo"},
        )

        other = "logs" if fx.enum == "NOTES" else "notes"
        mine = "notes" if fx.enum == "NOTES" else "logs"
        assert_data(
            self, result, {"search": [{mine: f"test foo {fx.field}", other: None}]}
        )

    def test_multiple_match(self, fx: Fixtures) -> None:
        result = graphql(
            fx.client,
            self.query,
            variables={"machine": "babette", "field": fx.enum, "key": "test"},
        )

        expected = [
            {
                ("notes" if fx.enum == "NOTES" else "logs"): f"test bar {fx.field}",
                "logs" if fx.enum == "NOTES" else "notes": None,
            },
            {
                ("notes" if fx.enum == "NOTES" else "logs"): f"test foo {fx.field}",
                "logs" if fx.enum == "NOTES" else "notes": None,
            },
        ]
        assert_data(self, result, {"search": expected})

    def test_only_matches_given_machine(self, fx: Fixtures) -> None:
        build = BuildFactory(machine="lighthouse")
        record = publisher.record(build)
        publisher.repo.build_records.save(record, **{fx.field: "test foo"})

        result = graphql(
            fx.client,
            self.query,
            variables={"machine": "lighthouse", "field": fx.enum, "key": "test"},
        )

        assert_data(
            self,
            result,
            {
                "search": [
                    {
                        "logs" if fx.enum == "NOTES" else "notes": None,
                        "notes" if fx.enum == "NOTES" else "logs": "test foo",
                    }
                ]
            },
        )

    def test_when_named_machine_does_not_exist(self, fx: Fixtures) -> None:
        result = graphql(
            fx.client,
            self.query,
            variables={"machine": "bogus", "field": "NOTES", "key": "test"},
        )

        assert_data(self, result, {"search": []})


@fixture(testkit.publisher)
def search_notes_query_builds(_fixtures: Fixtures) -> list[Build]:
    build1 = BuildFactory()
    record = publisher.record(build1)
    publisher.repo.build_records.save(record, note="test foo")
    build2 = BuildFactory()
    record = publisher.record(build2)
    publisher.repo.build_records.save(record, note="test bar")

    return [build1, build2]


@given(testkit.tmpdir, testkit.publisher, search_notes_query_builds, testkit.client)
class SearchNotesQueryTestCase(TestCase):
    """tests for the searchNotes query"""

    query = """
    query ($machine: String!, $key: String!) {
     searchNotes(machine: $machine, key: $key) {
        id
        notes
      }
    }
    """

    def test_single_match(self, fixtures: Fixtures) -> None:
        result = graphql(
            fixtures.client, self.query, variables={"machine": "babette", "key": "foo"}
        )

        builds = fixtures.search_notes_query_builds
        assert_data(
            self, result, {"searchNotes": [{"id": builds[0].id, "notes": "test foo"}]}
        )

    def test_multiple_match(self, fixtures: Fixtures) -> None:
        result = graphql(
            fixtures.client, self.query, variables={"machine": "babette", "key": "test"}
        )

        builds = fixtures.search_notes_query_builds
        assert_data(
            self,
            result,
            {
                "searchNotes": [
                    {"id": builds[1].id, "notes": "test bar"},
                    {"id": builds[0].id, "notes": "test foo"},
                ]
            },
        )

    def test_only_matches_given_machine(self, fixtures: Fixtures) -> None:
        build = BuildFactory(machine="lighthouse")
        publisher.pull(build)
        record = publisher.record(build)
        publisher.repo.build_records.save(record, note="test foo")

        result = graphql(
            fixtures.client,
            self.query,
            variables={"machine": "lighthouse", "key": "test"},
        )

        assert_data(
            self, result, {"searchNotes": [{"id": build.id, "notes": "test foo"}]}
        )

    def test_when_named_machine_does_not_exist(self, fixtures: Fixtures) -> None:
        result = graphql(
            fixtures.client, self.query, variables={"machine": "bogus", "key": "test"}
        )

        assert_data(self, result, {"searchNotes": []})


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class WorkingTestCase(TestCase):
    query = """
    {
      working {
          id
      }
    }
    """

    def test(self, fixtures: Fixtures) -> None:
        publisher.pull(BuildFactory())
        publisher.pull(BuildFactory(machine="lighthouse"))
        working = BuildFactory()
        publisher.repo.build_records.save(
            BuildRecord(working.machine, working.build_id)
        )

        result = graphql(fixtures.client, self.query)

        assert_data(self, result, {"working": [{"id": working.id}]})


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class VersionTestCase(TestCase):
    maxDiff = None
    query = """query { version }"""

    def test(self, fixtures: Fixtures) -> None:
        result = graphql(fixtures.client, self.query)
        version = get_version()

        assert_data(self, result, {"version": version})


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class CreateRepoTestCase(TestCase):
    """Tests for the createRepo mutation"""

    query = """
    mutation ($name: String!, $repo: String!, $branch: String!) {
     createRepo(name: $name, repo: $repo, branch: $branch) {
        message
      }
    }
    """

    def test_creates_repo_when_does_not_exist(self, fixtures: Fixtures) -> None:
        result = graphql(
            fixtures.client,
            self.query,
            variables={
                "name": "gentoo",
                "repo": "https://anongit.gentoo.org/git/repo/gentoo.git",
                "branch": "master",
            },
        )

        assert_data(self, result, {"createRepo": None})
        self.assertTrue(publisher.jenkins.project_exists(ProjectPath("repos/gentoo")))

    def test_returns_error_when_already_exists(self, fixtures: Fixtures) -> None:
        publisher.jenkins.make_folder(ProjectPath("repos"))
        publisher.jenkins.create_repo_job(
            EbuildRepo(name="gentoo", url="foo", branch="master")
        )

        result = graphql(
            fixtures.client,
            self.query,
            variables={
                "name": "gentoo",
                "repo": "https://anongit.gentoo.org/git/repo/gentoo.git",
                "branch": "master",
            },
        )

        assert_data(
            self, result, {"createRepo": {"message": "FileExistsError: repos/gentoo"}}
        )


@given(testkit.tmpdir, testkit.publisher, testkit.client)
class CreateMachineTestCase(TestCase):
    """Tests for the createMachine mutation"""

    query = """
    mutation (
        $name: String!, $repo: String!, $branch: String!, $ebuildRepos: [String!]!
    ) {
     createMachine(
         name: $name, repo: $repo, branch: $branch, ebuildRepos: $ebuildRepos
     ) {
        message
      }
    }
    """

    def test_creates_machine_when_does_not_exist(self, fixtures: Fixtures) -> None:
        result = graphql(
            fixtures.client,
            self.query,
            variables={
                "name": "babette",
                "repo": "https://github.com/enku/gbp-machines.git",
                "branch": "master",
                "ebuildRepos": ["gentoo"],
            },
        )

        assert_data(self, result, {"createMachine": None})
        self.assertTrue(publisher.jenkins.project_exists(ProjectPath("babette")))

    def test_returns_error_when_already_exists(self, fixtures: Fixtures) -> None:
        job = MachineJob(
            name="babette",
            repo=Repo(url="https://github.com/enku/gbp-machines.git", branch="master"),
            ebuild_repos=["gentoo"],
        )
        publisher.jenkins.create_machine_job(job)

        result = graphql(
            fixtures.client,
            self.query,
            variables={
                "name": "babette",
                "repo": "https://github.com/enku/gbp-machines.git",
                "branch": "master",
                "ebuildRepos": ["gentoo"],
            },
        )

        assert_data(
            self, result, {"createMachine": {"message": "FileExistsError: babette"}}
        )


@given(testkit.client)
class PluginsTestCase(TestCase):
    query = """query { plugins { name version description }}"""

    def test(self, fixtures: Fixtures) -> None:
        installed_plugins = plugins.get_plugins()
        self.assertGreaterEqual(len(installed_plugins), 1, "No installed plugins?!")

        result = graphql(fixtures.client, self.query)

        expected = [
            {"name": p.name, "version": p.version, "description": p.description}
            for p in installed_plugins
        ]
        assert_data(self, result, {"plugins": expected})


@given(
    testkit.client,
    testkit.builds,
    testkit.publisher,
    clear_cache=lambda _: cache_clear(),
)
@where(builds__machines=["babette", "lighthouse", "polaris"], builds__per_day=3)
class StatsTests(TestCase):
    query = """query {
      stats {
        machines
        machineInfo {
          machine
          buildCount
          builds { id }
          latestBuild {
            id
            packages(buildId: true)
          }
          publishedBuild { id }
          tagInfo { tag build { id } }
          packageCount
        }
      }
    }"""

    def test(self, fixtures: Fixtures) -> None:
        # pylint: disable=undefined-loop-variable
        records: dict[str, list[BuildRecord]] = {}
        for machine, builds in fixtures.builds.items():
            records[machine] = []
            for build in builds:
                publisher.pull(build)
                records[machine].append(publisher.record(build))
            publisher.publish(build)
            publisher.tag(build, f"{build.machine}-test")

        result = graphql(fixtures.client, self.query)

        expected = {
            "machines": list(records),
            "machineInfo": [
                {
                    "buildCount": 3,
                    "builds": [
                        {"id": str(build)}
                        for build in sorted(
                            mrecords, key=lambda b: b.completed or 0, reverse=True
                        )
                    ],
                    "latestBuild": {
                        "id": str(mrecords[-1]),
                        "packages": [
                            p.cpvb() for p in publisher.get_packages(mrecords[-1])
                        ],
                    },
                    "machine": machine,
                    "publishedBuild": {"id": str(mrecords[-1])},
                    "tagInfo": [
                        {"tag": f"{machine}-test", "build": {"id": str(mrecords[-1])}}
                    ],
                    "packageCount": 12,
                }
                for machine, mrecords in records.items()
            ],
        }
        assert_data(self, result, {"stats": expected})


class DateScalarTests(TestCase):
    def test_from_string(self) -> None:
        value = "2025-10-08"

        parsed = scalars.parse_date_value(value)

        self.assertEqual(parsed, DATE)

    def test_to_string(self) -> None:
        serialized = scalars.serialize_date(DATE)

        self.assertEqual(serialized, "2025-10-08")


class DateTimeScalarTests(TestCase):
    def test_from_string(self) -> None:
        value = "2025-07-14T15:45:30+05:30"

        parsed = scalars.parse_datetime_value(value)

        self.assertEqual(parsed, TIMESTAMP)

    def test_to_string(self) -> None:
        serialized = scalars.serialize_datetime(TIMESTAMP)

        self.assertEqual(serialized, "2025-07-14T15:45:30+05:30")
