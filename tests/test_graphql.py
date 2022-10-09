"""Tests for the GraphQL interface for Gentoo Build Publisher"""
# pylint: disable=missing-docstring,too-many-lines
import datetime as dt
import json
from typing import Any
from unittest import mock

from django.test.client import Client
from graphql import GraphQLError, GraphQLResolveInfo

from gentoo_build_publisher.graphql import require_localhost
from gentoo_build_publisher.jenkins import ProjectPath
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import Content
from gentoo_build_publisher.utils import get_version, utctime

from . import TestCase
from .factories import PACKAGE_INDEX, BuildFactory, BuildModelFactory

Mock = mock.Mock


def execute(query, variables=None):
    client = Client()
    response = client.post(
        "/graphql",
        {"query": query, "variables": variables},
        content_type="application/json",
    )

    return json.loads(response.content)


def assert_data(test_case: TestCase, result: dict, expected: dict):
    test_case.assertEqual(result, {"data": expected})


class BuildQueryTestCase(TestCase):
    """Tests for the build query"""

    maxDiff = None

    def test(self):
        build = BuildFactory()
        self.artifact_builder.timer = 1646115094
        self.artifact_builder.build(build, "x11-wm/mutter-41.3")
        self.artifact_builder.build(build, "acct-group/sgx-0", repo="marduk")

        with mock.patch("gentoo_build_publisher.publisher.utctime") as mock_utctime:
            mock_utctime.return_value = utctime(dt.datetime(2022, 3, 1, 6, 28, 44))
            self.publisher.pull(build)

        self.publisher.tag(build, "prod")

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

        result = execute(query, variables={"id": build.id})

        expected = {
            "build": {
                "id": build.id,
                "machine": build.machine,
                "pulled": True,
                "published": False,
                "tags": ["prod"],
                "logs": "foo\n",
                "built": "2022-03-01T06:28:44+00:00",
                "submitted": "2022-03-01T06:28:44+00:00",
                "packagesBuilt": [
                    {"cpv": "acct-group/sgx-0"},
                    {"cpv": "x11-wm/mutter-41.3"},
                ],
            }
        }

        assert_data(self, result, expected)

    def test_packages(self):
        # given the pulled build with packages
        build = BuildFactory()
        self.publisher.pull(build)

        # when we query the build's packages
        query = """
        query ($id: ID!) {
          build(id: $id) {
            packages
          }
        }
        """
        result = execute(query, {"id": build.id})

        # Then we get the list of packages in the build
        assert_data(self, result, {"build": {"packages": PACKAGE_INDEX}})

    def test_packages_when_not_pulled_returns_none(self):
        # given the unpulled package
        build = BuildFactory()
        self.publisher.records.save(self.publisher.record(build))

        # when we query the build's packages
        query = """
        query ($id: ID!) {
          build(id: $id) {
            packages
          }
        }
        """
        result = execute(query, {"id": build.id})

        # Then none is returned
        assert_data(self, result, {"build": {"packages": None}})

    def test_packages_should_return_none_when_package_index_missing(self):
        # given the pulled build with index file missing
        build = BuildFactory()
        self.publisher.pull(build)

        (self.publisher.storage.get_path(build, Content.BINPKGS) / "Packages").unlink()

        # when we query the build's packages
        query = """
        query ($id: ID!) {
          build(id: $id) {
            packages
          }
        }
        """
        result = execute(query, {"id": build.id})

        # Then none is returned
        assert_data(self, result, {"build": {"packages": None}})

    def test_packagesbuild_should_return_error_when_gbpjson_missing(self):
        # given the pulled build with gbp.json missing
        build = BuildFactory()
        self.publisher.pull(build)
        (self.publisher.storage.get_path(build, Content.BINPKGS) / "gbp.json").unlink()

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
        result = execute(query, {"id": build.id})

        self.assertEqual(
            result["data"]["build"],
            {"id": build.id, "machine": build.machine, "packagesBuilt": None},
        )
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["message"], "Packages built unknown")
        self.assertEqual(result["errors"][0]["path"], ["build", "packagesBuilt"])


class BuildsQueryTestCase(TestCase):
    """Tests for the builds query"""

    maxDiff = None

    def test(self):
        now = dt.datetime(2021, 9, 30, 20, 17, tzinfo=dt.timezone.utc)
        builds = BuildFactory.create_batch(3)

        for build in builds:
            record = self.publisher.record(build)
            self.publisher.records.save(record, completed=now)

        builds.sort(key=lambda build: build.build_id, reverse=True)
        query = """
        query ($machine: String!) {
          builds(machine: $machine) {
            id
            completed
          }
        }
        """

        result = execute(query, variables={"machine": builds[0].machine})

        expected = [
            {"id": build.id, "completed": "2021-09-30T20:17:00+00:00"}
            for build in builds
        ]

        assert_data(self, result, {"builds": expected})

    def test_older_build_pulled_after_newer_should_not_sort_before(self):
        # Build first build
        first_build = BuildFactory(build_id="lighthouse.10000")
        self.publisher.jenkins.artifact_builder.build_info(first_build)

        # Wait one hour
        self.publisher.jenkins.artifact_builder.advance(3600)

        # Build second build
        second_build = BuildFactory(build_id="lighthouse.10001")
        self.publisher.jenkins.artifact_builder.build_info(second_build)

        # Pull second build
        self.publisher.pull(second_build)

        # Pull first build
        self.publisher.pull(first_build)

        # Query the machine's builds
        query = """
        query ($machine: String!) {
          builds(machine: $machine) {
            id
          }
        }
        """
        result = execute(query, variables={"machine": "lighthouse"})

        assert_data(
            self,
            result,
            {"builds": [{"id": "lighthouse.10001"}, {"id": "lighthouse.10000"}]},
        )


class LatestQueryTestCase(TestCase):
    """Tests for the latest query"""

    def setUp(self):
        super().setUp()

        BuildModelFactory.create(
            built=dt.datetime(2021, 4, 25, 18, 0, tzinfo=dt.timezone.utc),
            submitted=dt.datetime(2021, 4, 25, 18, 10, tzinfo=dt.timezone.utc),
            completed=dt.datetime(2021, 4, 28, 17, 13, tzinfo=dt.timezone.utc),
        )
        self.latest = BuildModelFactory.create(
            built=dt.datetime(2022, 2, 25, 12, 8, tzinfo=dt.timezone.utc),
            submitted=dt.datetime(2022, 2, 25, 0, 15, tzinfo=dt.timezone.utc),
            completed=dt.datetime(2022, 2, 25, 0, 20, tzinfo=dt.timezone.utc),
        )
        BuildModelFactory.create(
            submitted=dt.datetime(2022, 2, 25, 6, 50, tzinfo=dt.timezone.utc),
        )

    def test_when_no_builds_should_respond_with_none(self):
        query = """
        {
          latest(machine: "bogus") {
            id
          }
        }
        """
        result = execute(query)

        assert_data(self, result, {"latest": None})

    def test_should_return_the_latest_submitted_completed(self):
        query = """
        {
          latest(machine: "babette") {
            id
          }
        }
        """
        result = execute(query)

        assert_data(self, result, {"latest": {"id": str(self.latest)}})


class DiffQueryTestCase(TestCase):
    """Tests for the diff query"""

    def setUp(self):
        super().setUp()

        # Given the first build with tar-1.34
        self.left = BuildFactory()
        old = self.artifact_builder.build(self.left, "app-arch/tar-1.34")
        self.publisher.pull(self.left)

        # Given the second build with tar-1.35
        self.right = BuildFactory()
        self.artifact_builder.build(self.right, "app-arch/tar-1.35")
        self.artifact_builder.remove(self.right, old)
        self.publisher.pull(self.right)

    def test(self):
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
        variables = {"left": self.left.id, "right": self.right.id}
        result = execute(query, variables=variables)

        # Then the differences are given between the two builds
        expected = {
            "diff": {
                "left": {"id": self.left.id},
                "right": {"id": self.right.id},
                "items": [
                    {"item": "app-arch/tar-1.34-1", "status": "REMOVED"},
                    {"item": "app-arch/tar-1.35-1", "status": "ADDED"},
                ],
            }
        }
        assert_data(self, result, expected)

    def test_should_exclude_build_data_when_not_selected(self):
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
        variables = {"left": self.left.id, "right": self.right.id}

        result = execute(query, variables=variables)

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

    def test_should_return_error_when_left_does_not_exist(self):
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
        variables = {"left": "bogus.1", "right": self.right.id}
        result = execute(query, variables=variables)

        # Then an error is returned
        self.assertEqual(result["data"]["diff"], None)
        self.assertEqual(
            result["errors"][0]["message"], "Build does not exist: bogus.1"
        )

    def test_should_return_error_when_right_does_not_exist(self):
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
        variables = {"left": self.left.id, "right": "bogus.1"}
        result = execute(query, variables=variables)

        # Then an error is returned
        self.assertEqual(result["data"]["diff"], None)
        self.assertEqual(
            result["errors"][0]["message"], "Build does not exist: bogus.1"
        )


class MachinesQueryTestCase(TestCase):
    """Tests for the machines query"""

    maxDiff = None

    def test(self):
        babette_builds = BuildFactory.create_batch(3, machine="babette")
        lighthouse_builds = BuildFactory.create_batch(3, machine="lighthouse")

        for build in babette_builds + lighthouse_builds:
            self.publisher.pull(build)

        # publish a build
        build = babette_builds[-1]
        self.publisher.publish(build)

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

        result = execute(query)

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

    def test_only_machine(self):
        # basically test that only selecting the name doesn't query other infos
        # (coverage.py)
        for build in BuildFactory.create_batch(
            2, machine="babette"
        ) + BuildFactory.create_batch(3, machine="lighthouse"):
            self.publisher.pull(build)

        query = """
        {
          machines {
            machine
          }
        }
        """
        result = execute(query)

        assert_data(
            self,
            result,
            {"machines": [{"machine": "babette"}, {"machine": "lighthouse"}]},
        )

    def test_latest_build_is_published(self):
        build = BuildFactory.create()
        self.publisher.pull(build)

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
        result = execute(query)

        self.assertFalse(result["data"]["machines"][0]["latestBuild"]["published"])

        self.publisher.publish(build)
        result = execute(query)
        self.assertTrue(result["data"]["machines"][0]["latestBuild"]["published"])


class PublishMutationTestCase(TestCase):
    """Tests for the publish mutation"""

    def test_publish_when_pulled(self):
        """Should publish builds"""
        build = BuildFactory()
        self.publisher.pull(build)

        query = """
        mutation ($id: ID!) {
          publish(id: $id) {
            publishedBuild {
              id
            }
          }
        }
        """
        result = execute(query, variables={"id": build.id})

        assert_data(self, result, {"publish": {"publishedBuild": {"id": build.id}}})

    def test_publish_when_not_pulled(self):
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
        with mock.patch(
            "gentoo_build_publisher.graphql.publish_build.delay"
        ) as publish_delay:
            execute(query)

        publish_delay.assert_called_once_with("babette.193")


class PullMutationTestCase(TestCase):
    """Tests for the pull mutation"""

    def test(self):
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
        with mock.patch("gentoo_build_publisher.graphql.pull_build") as mock_pull:
            result = execute(query, variables={"id": build.id})

        assert_data(self, result, {"pull": {"publishedBuild": None}})
        mock_pull.delay.assert_called_once_with(build.id)


class ScheduleBuildMutationTestCase(TestCase):
    """Tests for the build mutation"""

    maxDiff = None

    def test(self):
        query = 'mutation { scheduleBuild(machine: "babette") }'

        with mock.patch.object(self.publisher, "schedule_build") as mock_schedule_build:
            mock_schedule_build.return_value = (
                "https://jenkins.invalid/queue/item/31528/"
            )
            result = execute(query)

        self.assertEqual(
            result,
            {"data": {"scheduleBuild": "https://jenkins.invalid/queue/item/31528/"}},
        )
        mock_schedule_build.assert_called_once_with("babette")

    def test_should_return_error_when_schedule_build_fails(self):
        query = 'mutation { scheduleBuild(machine: "babette") }'

        with mock.patch.object(self.publisher, "schedule_build") as mock_schedule_build:
            mock_schedule_build.side_effect = Exception("The end is near")
            result = execute(query)

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


class KeepBuildMutationTestCase(TestCase):
    """Tests for the keep mutation"""

    maxDiff = None

    def test_should_keep_existing_build(self):
        model = BuildModelFactory.create()
        query = """
        mutation ($id: ID!) {
         keepBuild(id: $id) {
            keep
          }
        }
        """
        result = execute(query, variables={"id": str(model)})

        assert_data(self, result, {"keepBuild": {"keep": True}})

    def test_should_return_none_when_build_doesnt_exist(self):
        query = """
        mutation KeepBuild($id: ID!) {
         keepBuild(id: $id) {
            keep
          }
        }
        """

        result = execute(query, variables={"id": "bogus.309"})

        assert_data(self, result, {"keepBuild": None})


class ReleaseBuildMutationTestCase(TestCase):
    """Tests for the releaseBuild mutation"""

    def test_should_release_existing_build(self):
        build = BuildFactory()
        record = self.publisher.record(build)
        self.publisher.records.save(record, keep=True)

        query = """
        mutation ($id: ID!) {
         releaseBuild(id: $id) {
            keep
          }
        }
        """

        result = execute(query, variables={"id": build.id})

        assert_data(self, result, {"releaseBuild": {"keep": False}})

    def test_should_return_none_when_build_doesnt_exist(self):
        query = """
        mutation ($id: ID!) {
         releaseBuild(id: $id) {
            keep
          }
        }
        """

        result = execute(query, variables={"id": "bogus.309"})

        assert_data(self, result, {"releaseBuild": None})


class CreateNoteMutationTestCase(TestCase):
    """Tests for the createNote mutation"""

    def test_set_text(self):
        model = BuildModelFactory.create()
        note_text = "Hello, world!"
        query = """
        mutation ($id: ID!, $note: String) {
         createNote(id: $id, note: $note) {
            notes
          }
        }
        """

        result = execute(query, variables={"id": str(model), "note": note_text})

        assert_data(self, result, {"createNote": {"notes": note_text}})
        model.refresh_from_db()
        self.assertEqual(model.buildnote.note, note_text)

    def test_set_none(self):
        build = BuildFactory()
        self.publisher.pull(build)

        query = """
        mutation ($id: ID!, $note: String) {
         createNote(id: $id, note: $note) {
            notes
          }
        }
        """

        result = execute(query, variables={"id": build.id, "note": None})

        assert_data(self, result, {"createNote": {"notes": None}})

        record = self.publisher.record(build)
        self.assertEqual(record.note, None)

    def test_should_return_none_when_build_doesnt_exist(self):
        query = """
        mutation ($id: ID!, $note: String) {
         createNote(id: $id, note: $note) {
            notes
          }
        }
        """

        result = execute(query, variables={"id": "bogus.309", "note": None})

        assert_data(self, result, {"createNote": None})


class TagsTestCase(TestCase):
    def test_createbuildtag_mutation_tags_the_build(self):
        build = BuildFactory()
        self.publisher.pull(build)
        query = """
        mutation ($id: ID!, $tag: String!) {
         createBuildTag(id: $id, tag: $tag) {
            tags
          }
        }
        """

        result = execute(query, variables={"id": build.id, "tag": "prod"})

        assert_data(self, result, {"createBuildTag": {"tags": ["prod"]}})

    def test_removebuildtag_mutation_removes_tag_from_the_build(self):
        build = BuildFactory()
        self.publisher.pull(build)
        self.publisher.tag(build, "prod")

        query = """
        mutation ($machine: String!, $tag: String!) {
         removeBuildTag(machine: $machine, tag: $tag) {
            tags
          }
        }
        """

        result = execute(query, variables={"machine": build.machine, "tag": "prod"})

        assert_data(self, result, {"removeBuildTag": {"tags": []}})

    def test_resolvetag_query_resolves_tag(self):
        build = BuildFactory()
        self.publisher.pull(build)
        self.publisher.tag(build, "prod")

        query = """
        query ($machine: String!, $tag: String!) {
         resolveBuildTag(machine: $machine, tag: $tag) {
            id
          }
        }
        """

        result = execute(query, variables={"machine": build.machine, "tag": "prod"})

        assert_data(self, result, {"resolveBuildTag": {"id": build.id}})

    def test_resolvetag_query_resolves_to_none_when_tag_does_not_exist(self):
        build = BuildFactory()
        self.publisher.pull(build)

        query = """
        query ($machine: String!, $tag: String!) {
         resolveBuildTag(machine: $machine, tag: $tag) {
            id
          }
        }
        """

        result = execute(query, variables={"machine": build.machine, "tag": "prod"})

        assert_data(self, result, {"resolveBuildTag": None})


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

    def setUp(self):
        super().setUp()

        self.build1 = BuildFactory()
        record = self.publisher.record(self.build1)
        self.publisher.records.save(record, note="test foo")
        self.build2 = BuildFactory()
        record = self.publisher.record(self.build2)
        self.publisher.records.save(record, note="test bar")

    def test_single_match(self):
        result = execute(self.query, variables={"machine": "babette", "key": "foo"})

        assert_data(
            self, result, {"searchNotes": [{"id": self.build1.id, "notes": "test foo"}]}
        )

    def test_multiple_match(self):
        result = execute(self.query, variables={"machine": "babette", "key": "test"})

        assert_data(
            self,
            result,
            {
                "searchNotes": [
                    {"id": self.build2.id, "notes": "test bar"},
                    {"id": self.build1.id, "notes": "test foo"},
                ]
            },
        )

    def test_only_matches_given_machine(self):
        build = BuildFactory(machine="lighthouse")
        self.publisher.pull(build)
        record = self.publisher.record(build)
        self.publisher.records.save(record, note="test foo")

        result = execute(self.query, variables={"machine": "lighthouse", "key": "test"})

        assert_data(
            self,
            result,
            {"searchNotes": [{"id": build.id, "notes": "test foo"}]},
        )

    def test_when_named_machine_does_not_exist(self):
        result = execute(self.query, variables={"machine": "bogus", "key": "test"})

        assert_data(self, result, {"searchNotes": []})


class WorkingTestCase(TestCase):
    query = """
    {
      working {
          id
      }
    }
    """

    def test(self):
        self.publisher.pull(BuildFactory())
        self.publisher.pull(BuildFactory(machine="lighthouse"))
        working = BuildFactory()
        self.publisher.records.save(BuildRecord(working.id))

        result = execute(self.query)

        assert_data(self, result, {"working": [{"id": working.id}]})


class VersionTestCase(TestCase):
    maxDiff = None

    query = """query { version }"""

    def test(self):
        result = execute(self.query)
        version = get_version()

        assert_data(self, result, {"version": version})


class CreateRepoTestCase(TestCase):
    """Tests for the createRepo mutation"""

    query = """
    mutation ($name: String!, $repo: String!, $branch: String!) {
     createRepo(name: $name, repo: $repo, branch: $branch) {
        message
      }
    }
    """

    def test_creates_repo_when_does_not_exist(self):
        result = execute(
            self.query,
            variables={
                "name": "gentoo",
                "repo": "https://anongit.gentoo.org/git/repo/gentoo.git",
                "branch": "master",
            },
        )

        assert_data(self, result, {"createRepo": None})
        self.assertTrue(
            self.publisher.jenkins.project_exists(ProjectPath("repos/gentoo"))
        )

    def test_returns_error_when_already_exists(self):
        self.publisher.jenkins.make_folder(ProjectPath("repos"))
        self.publisher.jenkins.create_repo_job("gentoo", "foo", "master")

        result = execute(
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


class CreateMachineTestCase(TestCase):
    """Tests for the createMachine mutation"""

    query = """
    mutation ($name: String!, $repo: String!, $branch: String!, $ebuild_repos: [String!]!) {
     createMachine(name: $name, repo: $repo, branch: $branch, ebuild_repos: $ebuild_repos) {
        message
      }
    }
    """

    def test_creates_machine_when_does_not_exist(self):
        result = execute(
            self.query,
            variables={
                "name": "babette",
                "repo": "https://github.com/enku/gbp-machines.git",
                "branch": "master",
                "ebuild_repos": ["gentoo"],
            },
        )

        assert_data(self, result, {"createMachine": None})
        self.assertTrue(self.publisher.jenkins.project_exists(ProjectPath("babette")))

    def test_returns_error_when_already_exists(self):
        self.publisher.jenkins.create_machine_job(
            "babette", "https://github.com/enku/gbp-machines.git", "master", ["gentoo"]
        )

        result = execute(
            self.query,
            variables={
                "name": "babette",
                "repo": "https://github.com/enku/gbp-machines.git",
                "branch": "master",
                "ebuild_repos": ["gentoo"],
            },
        )

        assert_data(
            self,
            result,
            {"createMachine": {"message": "FileExistsError: babette"}},
        )


@require_localhost
def dummy_resolver(
    _obj: Any, _info: GraphQLResolveInfo, *args: Any, **kwargs: Any
) -> str:
    """Test resolver for RequireLocalhostTestCase"""
    return "permitted"


class RequireLocalhostTestCase(TestCase):
    def test_allows_ipv4_localhost(self):
        remote_ip = "127.0.0.1"
        info = Mock(context={"request": Mock(environ={"REMOTE_ADDR": remote_ip})})

        self.assertEqual(dummy_resolver(None, info), "permitted")

    def test_allows_ipv6_localhost(self):
        remote_ip = "::1"
        info = Mock(context={"request": Mock(environ={"REMOTE_ADDR": remote_ip})})

        self.assertEqual(dummy_resolver(None, info), "permitted")

    def test_allows_literal_localhost(self):
        # I'm not sure if this ever could happen, but...
        remote_ip = "localhost"
        info = Mock(context={"request": Mock(environ={"REMOTE_ADDR": remote_ip})})

        self.assertEqual(dummy_resolver(None, info), "permitted")

    def test_returns_error_when_not_localhost(self):
        remote_ip = "192.0.2.23"
        info = Mock(context={"request": Mock(environ={"REMOTE_ADDR": remote_ip})})

        with self.assertRaises(GraphQLError) as context:
            dummy_resolver(None, info)

        self.assertTrue(str(context.exception).startswith(""))

    def test_returns_error_when_no_remote_addr_in_request(self):
        info = Mock(context={"request": Mock(environ={})})

        with self.assertRaises(GraphQLError) as context:
            dummy_resolver(None, info)

        self.assertTrue(str(context.exception).startswith("Unauthorized to resolve "))

    def test_returns_error_when_going_through_reverse_proxy(self):
        # Fix for gunicorn
        environ = {
            "CONTENT_TYPE": "application/json",
            "HTTP_X_FORWARDED_FOR": "192.0.2.23",
            "PATH_INFO": "/graphql",
            "REMOTE_ADDR": "127.0.0.1",
        }
        info = Mock(context={"request": Mock(environ=environ)})

        with self.assertRaises(GraphQLError) as context:
            dummy_resolver(None, info)

        self.assertTrue(str(context.exception).startswith("Unauthorized to resolve "))
