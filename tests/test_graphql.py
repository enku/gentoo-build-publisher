"""Tests for the GraphQL interface for Gentoo Build Publisher"""

# pylint: disable=missing-docstring,too-many-lines
import datetime as dt
import os
from typing import Any
from unittest import mock

from graphql import GraphQLResolveInfo

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import apikey
from gentoo_build_publisher.graphql import (
    UnauthorizedError,
    load_schema,
    require_apikey,
    resolvers,
    type_defs,
)
from gentoo_build_publisher.jenkins import ProjectPath
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import (
    ApiKey,
    Build,
    Content,
    EbuildRepo,
    MachineJob,
    Repo,
)
from gentoo_build_publisher.utils import encode_basic_auth_data, get_version, time
from gentoo_build_publisher.worker import tasks

from . import TestCase, fixture, parametrized
from .factories import PACKAGE_INDEX, BuildFactory, BuildRecordFactory
from .fixture_types import Fixtures, SetupOptions
from .helpers import BUILD_LOGS, graphql

Mock = mock.Mock

SEARCH_PARAMS = [["NOTES", "note"], ["LOGS", "logs"]]


def assert_data(test_case: TestCase, result: dict, expected: dict) -> None:
    test_case.assertFalse(result.get("errors"))

    data = result["data"]

    test_case.assertEqual(data, expected)


@fixture.requires("tmpdir", "publisher", "client")
class BuildQueryTestCase(TestCase):
    """Tests for the build query"""

    maxDiff = None

    def test(self) -> None:
        build = BuildFactory()
        artifact_builder = publisher.jenkins.artifact_builder
        artifact_builder.timer = 1646115094
        artifact_builder.build(build, "x11-wm/mutter-41.3")
        artifact_builder.build(build, "acct-group/sgx-0", repo="marduk")

        with mock.patch("gentoo_build_publisher.publisher.utctime") as mock_utctime:
            mock_utctime.return_value = time.utctime(dt.datetime(2022, 3, 1, 6, 28, 44))
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
            }
          }
        }
        """

        result = graphql(self.fixtures.client, query, variables={"id": build.id})

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
                    {"cpv": "acct-group/sgx-0"},
                    {"cpv": "x11-wm/mutter-41.3"},
                ],
            }
        }

        assert_data(self, result, expected)

    def test_packages(self) -> None:
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
        result = graphql(self.fixtures.client, query, {"id": build.id})

        # Then we get the list of packages in the build
        assert_data(self, result, {"build": {"packages": PACKAGE_INDEX}})

    def test_packages_when_not_pulled_returns_none(self) -> None:
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
        result = graphql(self.fixtures.client, query, {"id": build.id})

        # Then none is returned
        assert_data(self, result, {"build": {"packages": None}})

    def test_packages_should_return_none_when_package_index_missing(self) -> None:
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
        result = graphql(self.fixtures.client, query, {"id": build.id})

        # Then none is returned
        assert_data(self, result, {"build": {"packages": None}})

    def test_packagesbuild_should_return_error_when_gbpjson_missing(self) -> None:
        # given the pulled build with gbp.json missing
        build = BuildFactory()
        publisher.pull(build)
        (publisher.storage.get_path(build, Content.BINPKGS) / "gbp.json").unlink()

        # when we query the build's packagesBuild
        query = """
        query ($id: ID!) {
          build(id: $id) {
            id
            machine
            packagesBuilt {
              cpv
            }
          }
        }
        """
        result = graphql(self.fixtures.client, query, {"id": build.id})

        self.assertEqual(
            result["data"]["build"],
            {"id": build.id, "machine": build.machine, "packagesBuilt": None},
        )
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["message"], "Packages built unknown")
        self.assertEqual(result["errors"][0]["path"], ["build", "packagesBuilt"])


@fixture.requires("tmpdir", "publisher", "client")
class BuildsQueryTestCase(TestCase):
    """Tests for the builds query"""

    maxDiff = None

    def test(self) -> None:
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
            self.fixtures.client, query, variables={"machine": builds[0].machine}
        )

        expected = [
            {"id": build.id, "completed": "2021-09-30T20:17:00+00:00"}
            for build in builds
        ]

        assert_data(self, result, {"builds": expected})

    def test_older_build_pulled_after_newer_should_not_sort_before(self) -> None:
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
        result = graphql(
            self.fixtures.client, query, variables={"machine": "lighthouse"}
        )

        assert_data(
            self,
            result,
            {"builds": [{"id": "lighthouse.10001"}, {"id": "lighthouse.10000"}]},
        )


@fixture.depends("publisher")
def latest(_options: SetupOptions, _fixtures: Fixtures) -> Build:
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
            submitted=dt.datetime(2022, 2, 25, 6, 50, tzinfo=dt.UTC),
        )
    )
    return latest_build


@fixture.requires("tmpdir", "publisher", latest, "client")
class LatestQueryTestCase(TestCase):
    """Tests for the latest query"""

    def test_when_no_builds_should_respond_with_none(self) -> None:
        query = """
        {
          latest(machine: "bogus") {
            id
          }
        }
        """
        result = graphql(self.fixtures.client, query)

        assert_data(self, result, {"latest": None})

    def test_should_return_the_latest_submitted_completed(self) -> None:
        query = """
        {
          latest(machine: "babette") {
            id
          }
        }
        """
        result = graphql(self.fixtures.client, query)

        assert_data(self, result, {"latest": {"id": str(self.fixtures.latest)}})


@fixture.depends("publisher")
def diff_query_builds(_options: SetupOptions, fixtures: Fixtures) -> dict[str, Build]:
    # Given the first build with tar-1.34
    left = BuildFactory()
    artifact_builder = fixtures.publisher.jenkins.artifact_builder
    old = artifact_builder.build(left, "app-arch/tar-1.34")
    publisher.pull(left)

    # Given the second build with tar-1.35
    right = BuildFactory()
    artifact_builder.build(right, "app-arch/tar-1.35")
    artifact_builder.remove(right, old)
    publisher.pull(right)

    return {"left": left, "right": right}


@fixture.requires("tmpdir", "publisher", diff_query_builds, "client")
class DiffQueryTestCase(TestCase):
    """Tests for the diff query"""

    def test(self) -> None:
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
        builds = self.fixtures.diff_query_builds
        variables = {
            "left": builds["left"].id,
            "right": builds["right"].id,
        }
        result = graphql(self.fixtures.client, query, variables=variables)

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

    def test_should_exclude_build_data_when_not_selected(self) -> None:
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
        builds = self.fixtures.diff_query_builds
        variables = {
            "left": builds["left"].id,
            "right": builds["right"].id,
        }

        result = graphql(self.fixtures.client, query, variables=variables)

        # Then the differences are given between the two builds
        expected = {
            "diff": {
                "items": [
                    {"item": "app-arch/tar-1.34-1", "status": "REMOVED"},
                    {"item": "app-arch/tar-1.35-1", "status": "ADDED"},
                ],
            }
        }
        assert_data(self, result, expected)

    def test_should_return_error_when_left_does_not_exist(self) -> None:
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
        builds = self.fixtures.diff_query_builds
        variables = {"left": "bogus.1", "right": builds["right"].id}
        result = graphql(self.fixtures.client, query, variables=variables)

        # Then an error is returned
        self.assertEqual(result["data"]["diff"], None)
        self.assertEqual(
            result["errors"][0]["message"], "Build does not exist: bogus.1"
        )

    def test_should_return_error_when_right_does_not_exist(self) -> None:
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
        builds = self.fixtures.diff_query_builds
        variables = {"left": builds["left"].id, "right": "bogus.1"}
        result = graphql(self.fixtures.client, query, variables=variables)

        # Then an error is returned
        self.assertEqual(result["data"]["diff"], None)
        self.assertEqual(
            result["errors"][0]["message"], "Build does not exist: bogus.1"
        )


@fixture.requires("tmpdir", "publisher", "client")
class MachinesQueryTestCase(TestCase):
    """Tests for the machines query"""

    maxDiff = None

    def test(self) -> None:
        babette_builds = BuildFactory.create_batch(3, machine="babette")
        lighthouse_builds = BuildFactory.create_batch(3, machine="lighthouse")

        for build in babette_builds + lighthouse_builds:
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
          }
        }
        """

        result = graphql(self.fixtures.client, query)

        expected = [
            {
                "machine": "babette",
                "buildCount": 3,
                "builds": [{"id": i.id} for i in reversed(babette_builds)],
                "latestBuild": {"id": build.id},
                "publishedBuild": {"id": build.id},
            },
            {
                "machine": "lighthouse",
                "buildCount": 3,
                "builds": [{"id": i.id} for i in reversed(lighthouse_builds)],
                "latestBuild": {"id": lighthouse_builds[-1].id},
                "publishedBuild": None,
            },
        ]
        assert_data(self, result, {"machines": expected})

    def test_only_machine(self) -> None:
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
        result = graphql(self.fixtures.client, query)

        assert_data(
            self,
            result,
            {"machines": [{"machine": "babette"}, {"machine": "lighthouse"}]},
        )

    def test_latest_build_is_published(self) -> None:
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
        result = graphql(self.fixtures.client, query)

        self.assertFalse(result["data"]["machines"][0]["latestBuild"]["published"])

        publisher.publish(build)
        result = graphql(self.fixtures.client, query)
        self.assertTrue(result["data"]["machines"][0]["latestBuild"]["published"])


@fixture.requires("tmpdir", "publisher", "client")
class PublishMutationTestCase(TestCase):
    """Tests for the publish mutation"""

    def test_publish_when_pulled(self) -> None:
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
        result = graphql(self.fixtures.client, query, variables={"id": build.id})

        assert_data(self, result, {"publish": {"publishedBuild": {"id": build.id}}})

    def test_publish_when_not_pulled(self) -> None:
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
        with mock.patch("gentoo_build_publisher.graphql.worker") as mock_worker:
            graphql(self.fixtures.client, query)

        mock_worker.run.assert_called_once_with(tasks.publish_build, "babette.193")


@fixture.requires("tmpdir", "publisher", "client")
class PullMutationTestCase(TestCase):
    """Tests for the pull mutation"""

    def test(self) -> None:
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
        with mock.patch("gentoo_build_publisher.graphql.worker") as mock_worker:
            result = graphql(self.fixtures.client, query, variables={"id": build.id})

        assert_data(self, result, {"pull": {"publishedBuild": None}})
        mock_worker.run.assert_called_once_with(
            tasks.pull_build, build.id, note=None, tags=None
        )

    def test_pull_with_note(self) -> None:
        build = BuildFactory()

        query = """
        mutation ($id: ID!, $note: String) {
          pull(id: $id, note: $note) {
            publishedBuild {
              id
            }
          }
        }"""
        with mock.patch("gentoo_build_publisher.graphql.worker") as mock_worker:
            result = graphql(
                self.fixtures.client,
                query,
                variables={"id": build.id, "note": "This is a test"},
            )

        assert_data(self, result, {"pull": {"publishedBuild": None}})
        mock_worker.run.assert_called_once_with(
            tasks.pull_build, build.id, note="This is a test", tags=None
        )

    def test_pull_with_tag(self) -> None:
        build = BuildFactory()

        query = """
        mutation ($id: ID!, $tags: [String!]) {
          pull(id: $id, tags: $tags) {
            publishedBuild {
              id
            }
          }
        }"""
        with mock.patch("gentoo_build_publisher.graphql.worker") as mock_worker:
            result = graphql(
                self.fixtures.client,
                query,
                variables={"id": build.id, "tags": ["emptytree"]},
            )

        assert_data(self, result, {"pull": {"publishedBuild": None}})
        mock_worker.run.assert_called_once_with(
            tasks.pull_build, build.id, note=None, tags=["emptytree"]
        )


@fixture.requires("tmpdir", "publisher", "client")
class ScheduleBuildMutationTestCase(TestCase):
    """Tests for the build mutation"""

    maxDiff = None

    def test(self) -> None:
        query = 'mutation { scheduleBuild(machine: "babette") }'

        with mock.patch.object(publisher, "schedule_build") as mock_schedule_build:
            mock_schedule_build.return_value = (
                "https://jenkins.invalid/queue/item/31528/"
            )
            result = graphql(self.fixtures.client, query)

        self.assertEqual(
            result,
            {"data": {"scheduleBuild": "https://jenkins.invalid/queue/item/31528/"}},
        )
        mock_schedule_build.assert_called_once_with("babette")

    def test_with_params(self) -> None:
        query = """mutation
          {
            scheduleBuild(
              machine: "babette",
              params: [{name: "BUILD_TARGET", value: "world"}],
            )
          }
        """

        with mock.patch.object(publisher, "schedule_build") as mock_schedule_build:
            mock_schedule_build.return_value = (
                "https://jenkins.invalid/queue/item/31528/"
            )
            result = graphql(self.fixtures.client, query)

        self.assertEqual(
            result,
            {"data": {"scheduleBuild": "https://jenkins.invalid/queue/item/31528/"}},
        )
        mock_schedule_build.assert_called_once_with("babette", BUILD_TARGET="world")

    def test_should_return_error_when_schedule_build_fails(self) -> None:
        query = 'mutation { scheduleBuild(machine: "babette") }'

        with mock.patch.object(publisher, "schedule_build") as mock_schedule_build:
            mock_schedule_build.side_effect = Exception("The end is near")
            result = graphql(self.fixtures.client, query)

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
        mock_schedule_build.assert_called_once_with("babette")


@fixture.requires("tmpdir", "publisher", "client")
class KeepBuildMutationTestCase(TestCase):
    """Tests for the keep mutation"""

    maxDiff = None

    def test_should_keep_existing_build(self) -> None:
        build = BuildFactory()
        publisher.pull(build)
        query = """
        mutation ($id: ID!) {
         keepBuild(id: $id) {
            keep
          }
        }
        """
        result = graphql(self.fixtures.client, query, variables={"id": str(build)})

        assert_data(self, result, {"keepBuild": {"keep": True}})

    def test_should_return_none_when_build_doesnt_exist(self) -> None:
        query = """
        mutation KeepBuild($id: ID!) {
         keepBuild(id: $id) {
            keep
          }
        }
        """

        result = graphql(self.fixtures.client, query, variables={"id": "bogus.309"})

        assert_data(self, result, {"keepBuild": None})


@fixture.requires("tmpdir", "publisher", "client")
class ReleaseBuildMutationTestCase(TestCase):
    """Tests for the releaseBuild mutation"""

    def test_should_release_existing_build(self) -> None:
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

        result = graphql(self.fixtures.client, query, variables={"id": build.id})

        assert_data(self, result, {"releaseBuild": {"keep": False}})

    def test_should_return_none_when_build_doesnt_exist(self) -> None:
        query = """
        mutation ($id: ID!) {
         releaseBuild(id: $id) {
            keep
          }
        }
        """

        result = graphql(self.fixtures.client, query, variables={"id": "bogus.309"})

        assert_data(self, result, {"releaseBuild": None})


@fixture.requires("tmpdir", "publisher", "client")
class CreateNoteMutationTestCase(TestCase):
    """Tests for the createNote mutation"""

    def test_set_text(self) -> None:
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
            self.fixtures.client, query, variables={"id": str(build), "note": note_text}
        )

        assert_data(self, result, {"createNote": {"notes": note_text}})
        record = publisher.repo.build_records.get(build)
        self.assertEqual(record.note, note_text)

    def test_set_none(self) -> None:
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
            self.fixtures.client, query, variables={"id": build.id, "note": None}
        )

        assert_data(self, result, {"createNote": {"notes": None}})

        record = publisher.record(build)
        self.assertEqual(record.note, None)

    def test_should_return_none_when_build_doesnt_exist(self) -> None:
        query = """
        mutation ($id: ID!, $note: String) {
         createNote(id: $id, note: $note) {
            notes
          }
        }
        """

        result = graphql(
            self.fixtures.client, query, variables={"id": "bogus.309", "note": None}
        )

        assert_data(self, result, {"createNote": None})


@fixture.requires("tmpdir", "publisher", "client")
class TagsTestCase(TestCase):
    def test_createbuildtag_mutation_tags_the_build(self) -> None:
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
            self.fixtures.client, query, variables={"id": build.id, "tag": "prod"}
        )

        assert_data(self, result, {"createBuildTag": {"tags": ["prod"]}})

    def test_removebuildtag_mutation_removes_tag_from_the_build(self) -> None:
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
            self.fixtures.client,
            query,
            variables={"machine": build.machine, "tag": "prod"},
        )

        assert_data(self, result, {"removeBuildTag": {"tags": []}})

    def test_resolvetag_query_resolves_tag(self) -> None:
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
            self.fixtures.client,
            query,
            variables={"machine": build.machine, "tag": "prod"},
        )

        assert_data(self, result, {"resolveBuildTag": {"id": build.id}})

    def test_resolvetag_query_resolves_to_none_when_tag_does_not_exist(self) -> None:
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
            self.fixtures.client,
            query,
            variables={"machine": build.machine, "tag": "prod"},
        )

        assert_data(self, result, {"resolveBuildTag": None})


def search_query_builds(_options: SetupOptions, _fixtures: Fixtures) -> list[Build]:
    for _, field in SEARCH_PARAMS:
        build1 = BuildFactory()
        record = publisher.record(build1)
        publisher.repo.build_records.save(record, **{field: f"test foo {field}"})
        build2 = BuildFactory()
        record = publisher.record(build2)
        publisher.repo.build_records.save(record, **{field: f"test bar {field}"})

    return [build1, build2]


@fixture.requires("tmpdir", "publisher", search_query_builds, "client")
class SearchQueryTestCase(TestCase):
    """Tests for the search query"""

    query = """
    query ($machine: String!, $field: SearchField!, $key: String!) {
     search(machine: $machine, field: $field, key: $key) {
        logs
        notes
      }
    }
    """

    @parametrized(SEARCH_PARAMS)
    def test_single_match(self, enum: str, field: str) -> None:
        result = graphql(
            self.fixtures.client,
            self.query,
            variables={"machine": "babette", "field": enum, "key": "foo"},
        )

        other = "logs" if enum == "NOTES" else "notes"
        mine = "notes" if enum == "NOTES" else "logs"
        assert_data(
            self, result, {"search": [{mine: f"test foo {field}", other: None}]}
        )

    @parametrized(SEARCH_PARAMS)
    def test_multiple_match(self, enum: str, field: str) -> None:
        result = graphql(
            self.fixtures.client,
            self.query,
            variables={"machine": "babette", "field": enum, "key": "test"},
        )

        expected = [
            {
                "notes" if enum == "NOTES" else "logs": f"test bar {field}",
                "logs" if enum == "NOTES" else "notes": None,
            },
            {
                "notes" if enum == "NOTES" else "logs": f"test foo {field}",
                "logs" if enum == "NOTES" else "notes": None,
            },
        ]
        assert_data(self, result, {"search": expected})

    @parametrized(SEARCH_PARAMS)
    def test_only_matches_given_machine(self, enum: str, field: str) -> None:
        build = BuildFactory(machine="lighthouse")
        record = publisher.record(build)
        publisher.repo.build_records.save(record, **{field: "test foo"})

        result = graphql(
            self.fixtures.client,
            self.query,
            variables={"machine": "lighthouse", "field": enum, "key": "test"},
        )

        assert_data(
            self,
            result,
            {
                "search": [
                    {
                        "logs" if enum == "NOTES" else "notes": None,
                        "notes" if enum == "NOTES" else "logs": "test foo",
                    }
                ]
            },
        )

    def test_when_named_machine_does_not_exist(self) -> None:
        result = graphql(
            self.fixtures.client,
            self.query,
            variables={"machine": "bogus", "field": "NOTES", "key": "test"},
        )

        assert_data(self, result, {"search": []})


@fixture.depends("publisher")
def search_notes_query_builds(
    _options: SetupOptions, _fixtures: Fixtures
) -> list[Build]:
    build1 = BuildFactory()
    record = publisher.record(build1)
    publisher.repo.build_records.save(record, note="test foo")
    build2 = BuildFactory()
    record = publisher.record(build2)
    publisher.repo.build_records.save(record, note="test bar")

    return [build1, build2]


@fixture.requires("tmpdir", "publisher", search_notes_query_builds, "client")
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

    def test_single_match(self) -> None:
        result = graphql(
            self.fixtures.client,
            self.query,
            variables={"machine": "babette", "key": "foo"},
        )

        builds = self.fixtures.search_notes_query_builds
        assert_data(
            self,
            result,
            {"searchNotes": [{"id": builds[0].id, "notes": "test foo"}]},
        )

    def test_multiple_match(self) -> None:
        result = graphql(
            self.fixtures.client,
            self.query,
            variables={"machine": "babette", "key": "test"},
        )

        builds = self.fixtures.search_notes_query_builds
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

    def test_only_matches_given_machine(self) -> None:
        build = BuildFactory(machine="lighthouse")
        publisher.pull(build)
        record = publisher.record(build)
        publisher.repo.build_records.save(record, note="test foo")

        result = graphql(
            self.fixtures.client,
            self.query,
            variables={"machine": "lighthouse", "key": "test"},
        )

        assert_data(
            self,
            result,
            {"searchNotes": [{"id": build.id, "notes": "test foo"}]},
        )

    def test_when_named_machine_does_not_exist(self) -> None:
        result = graphql(
            self.fixtures.client,
            self.query,
            variables={"machine": "bogus", "key": "test"},
        )

        assert_data(self, result, {"searchNotes": []})


@fixture.requires("tmpdir", "publisher", "client")
class WorkingTestCase(TestCase):
    query = """
    {
      working {
          id
      }
    }
    """

    def test(self) -> None:
        publisher.pull(BuildFactory())
        publisher.pull(BuildFactory(machine="lighthouse"))
        working = BuildFactory()
        publisher.repo.build_records.save(
            BuildRecord(working.machine, working.build_id)
        )

        result = graphql(self.fixtures.client, self.query)

        assert_data(self, result, {"working": [{"id": working.id}]})


@fixture.requires("tmpdir", "publisher", "client")
class VersionTestCase(TestCase):
    maxDiff = None
    query = """query { version }"""

    def test(self) -> None:
        result = graphql(self.fixtures.client, self.query)
        version = get_version()

        assert_data(self, result, {"version": version})


@fixture.requires("tmpdir", "publisher", "client")
class CreateRepoTestCase(TestCase):
    """Tests for the createRepo mutation"""

    query = """
    mutation ($name: String!, $repo: String!, $branch: String!) {
     createRepo(name: $name, repo: $repo, branch: $branch) {
        message
      }
    }
    """

    def test_creates_repo_when_does_not_exist(self) -> None:
        result = graphql(
            self.fixtures.client,
            self.query,
            variables={
                "name": "gentoo",
                "repo": "https://anongit.gentoo.org/git/repo/gentoo.git",
                "branch": "master",
            },
        )

        assert_data(self, result, {"createRepo": None})
        self.assertTrue(publisher.jenkins.project_exists(ProjectPath("repos/gentoo")))

    def test_returns_error_when_already_exists(self) -> None:
        publisher.jenkins.make_folder(ProjectPath("repos"))
        publisher.jenkins.create_repo_job(
            EbuildRepo(name="gentoo", url="foo", branch="master")
        )

        result = graphql(
            self.fixtures.client,
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


@fixture.requires("tmpdir", "publisher", "client")
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

    def test_creates_machine_when_does_not_exist(self) -> None:
        result = graphql(
            self.fixtures.client,
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

    def test_returns_error_when_already_exists(self) -> None:
        job = MachineJob(
            name="babette",
            repo=Repo(url="https://github.com/enku/gbp-machines.git", branch="master"),
            ebuild_repos=["gentoo"],
        )
        publisher.jenkins.create_machine_job(job)

        result = graphql(
            self.fixtures.client,
            self.query,
            variables={
                "name": "babette",
                "repo": "https://github.com/enku/gbp-machines.git",
                "branch": "master",
                "ebuildRepos": ["gentoo"],
            },
        )

        assert_data(
            self,
            result,
            {"createMachine": {"message": "FileExistsError: babette"}},
        )


@fixture.requires("tmpdir", "publisher", "client")
class MaybeRequiresAPIKeyTests(TestCase):
    query = 'mutation { scheduleBuild(machine: "babette") }'

    def test_enabled(self) -> None:
        with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_API_KEY_ENABLE": "yes"}):
            error = graphql(self.fixtures.client, self.query)["errors"][0]["message"]

        self.assertEqual(error, "Unauthorized to resolve scheduleBuild")

    def test_disabled(self) -> None:
        with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_API_KEY_ENABLE": "no"}):
            response = graphql(self.fixtures.client, self.query)

        self.assertNotIn("errors", response)


def dummy_resolver(
    _obj: Any, _info: GraphQLResolveInfo, *args: Any, **kwargs: Any
) -> str:
    """Test resolver"""
    return "permitted"


@fixture.requires("tmpdir", "publisher")
class RequireAPIKeyTestCase(TestCase):
    def test_good_apikey(self) -> None:
        name = "test"
        api_key = ApiKey(
            name=name,
            key=apikey.create_api_key(),
            created=dt.datetime(2024, 4, 27, 20, 17, tzinfo=dt.UTC),
        )
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, api_key.key)
        gql_context = {"request": Mock(headers={"Authorization": f"Basic {encoded}"})}
        info = Mock(context=gql_context)
        info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        self.assertEqual(resolver(None, info), "permitted")

    def test_good_key_updates_records_last_use(self) -> None:
        name = "test"
        api_key = ApiKey(
            name=name,
            key=apikey.create_api_key(),
            created=dt.datetime(2024, 4, 27, 20, 17, tzinfo=dt.UTC),
        )
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, api_key.key)
        gql_context = {"request": Mock(headers={"Authorization": f"Basic {encoded}"})}
        info = Mock(context=gql_context)
        info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        api_key = publisher.repo.api_keys.get(name)
        self.assertIs(api_key.last_used, None)

        resolver(None, info)

        api_key = publisher.repo.api_keys.get(name)
        self.assertIsNot(api_key.last_used, None, "The last_used field was not updated")

    def test_no_apikey(self) -> None:
        gql_context = {"request": Mock(headers={})}
        info = Mock(context=gql_context)
        info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        with self.assertRaises(UnauthorizedError) as context:
            resolver(None, info)

        self.assertEqual(
            str(context.exception), "Unauthorized to resolve dummy_resolver"
        )

    def test_bad_apikey(self) -> None:
        name = "test"
        api_key = ApiKey(
            name=name,
            key=apikey.create_api_key(),
            created=dt.datetime(2024, 4, 27, 20, 17, tzinfo=dt.UTC),
        )
        publisher.repo.api_keys.save(api_key)
        encoded = encode_basic_auth_data(name, "bogus")
        gql_context = {"request": Mock(headers={"Authorization": f"Basic {encoded}"})}
        info = Mock(context=gql_context)
        info.path.key = "dummy_resolver"
        resolver = require_apikey(dummy_resolver)

        with self.assertRaises(UnauthorizedError) as context:
            resolver(None, info)

        self.assertEqual(
            str(context.exception), "Unauthorized to resolve dummy_resolver"
        )


class LoadSchemaTests(TestCase):
    def test(self) -> None:
        schema = load_schema()

        self.assertEqual(schema, ([type_defs], resolvers))
