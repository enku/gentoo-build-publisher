"""Tests for the GraphQL interface for Gentoo Build Publisher"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
import json
from unittest import mock

from django.test.client import Client

from gentoo_build_publisher.build import Content

from . import PACKAGE_INDEX, TestCase
from .factories import BuildManFactory, BuildModelFactory


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

    def test(self):
        build = BuildManFactory.create()
        query = """query Build($name: String!, $number: Int!) {
            build(name: $name, number: $number) {
                name
                number
                pulled
                published
            }
        }
        """

        result = execute(query, variables={"name": build.name, "number": build.number})

        expected = {
            "build": {
                "name": build.name,
                "number": build.number,
                "pulled": False,
                "published": False,
            }
        }

        assert_data(self, result, expected)


class BuildsQueryTestCase(TestCase):
    """Tests for the builds query"""

    maxDiff = None

    def test(self):
        now = dt.datetime(2021, 9, 30, 20, 17, tzinfo=dt.timezone.utc)
        builds = BuildManFactory.create_batch(3, build_attr__build_model__completed=now)
        builds.sort(key=lambda build: build.number, reverse=True)
        query = """query Builds($name: String!) {
            builds(name: $name) {
                number
                completed
            }
        }
        """

        result = execute(query, variables={"name": builds[0].name})

        build_numbers = [build.number for build in builds]
        expected = [
            {"number": number, "completed": "2021-09-30T20:17:00+00:00"}
            for number in build_numbers
        ]

        assert_data(self, result, {"builds": expected})


class LatestQueryTestCase(TestCase):
    """Tests for the latest query"""

    def setUp(self):
        super().setUp()

        BuildModelFactory.create(
            submitted=dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc),
            completed=dt.datetime(1970, 1, 4, tzinfo=dt.timezone.utc),
        )
        self.latest = BuildModelFactory.create(
            submitted=dt.datetime(1970, 1, 2, tzinfo=dt.timezone.utc),
            completed=dt.datetime(1970, 1, 2, tzinfo=dt.timezone.utc),
        )
        BuildModelFactory.create(
            submitted=dt.datetime(1970, 1, 3, tzinfo=dt.timezone.utc),
        )

    def test_when_no_builds_should_respond_with_none(self):
        query = """{
            latest(name: "bogus") {
                number
            }
        }"""
        result = execute(query)

        assert_data(self, result, {"latest": None})

    def test_should_return_the_latest_submitted_completed(self):
        query = """{
            latest(name: "babette") {
                number
            }
        }"""
        result = execute(query)

        assert_data(self, result, {"latest": {"number": self.latest.number}})


class DiffQueryTestCase(TestCase):
    """Tests for the diff query"""

    def setUp(self):
        super().setUp()

        # Given the first build with tar-1.34
        self.left_bm = BuildManFactory.create()
        path = self.left_bm.storage_build.get_path(Content.BINPKGS) / "app-arch" / "tar"
        path.mkdir(parents=True)
        somefile = path / "tar-1.34-1.xpak"
        somefile.write_text("test")

        # Given the second build with tar-1.35
        self.right_bm = BuildManFactory.create()
        path = (
            self.right_bm.storage_build.get_path(Content.BINPKGS) / "app-arch" / "tar"
        )
        path.mkdir(parents=True)
        somefile = path / "tar-1.35-1.xpak"
        somefile.write_text("test")

    def test(self):
        # When we call get the diff view given the 2 builds
        left_bm = self.left_bm
        right_bm = self.right_bm

        query = """query Diff($left: BuildInput!, $right: BuildInput!) {
            diff(left: $left, right: $right) {
                left {
                    number
                }
                right {
                    number
                }
                items {
                    item
                    status
                }
            }
        }"""
        variables = {
            "left": {"name": left_bm.name, "number": left_bm.number},
            "right": {"name": right_bm.name, "number": right_bm.number},
        }
        result = execute(query, variables=variables)

        # Then the differences are given between the two builds
        expected = {
            "diff": {
                "left": {"number": left_bm.number},
                "right": {"number": right_bm.number},
                "items": [
                    {"item": "app-arch/tar-1.34-1", "status": "REMOVED"},
                    {"item": "app-arch/tar-1.35-1", "status": "ADDED"},
                ],
            }
        }
        assert_data(self, result, expected)

    def test_should_exclude_build_data_when_not_selected(self):
        left_bm = self.left_bm
        right_bm = self.right_bm

        query = """query Diff($left: BuildInput!, $right: BuildInput!) {
            diff(left: $left, right: $right) {
                items {
                    item
                    status
                }
            }
        }"""
        variables = {
            "left": {"name": left_bm.name, "number": left_bm.number},
            "right": {"name": right_bm.name, "number": right_bm.number},
        }
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

    def test_should_return_none_when_left_does_not_exist(self):
        right_bm = self.right_bm

        query = """query Diff($left: BuildInput!, $right: BuildInput!) {
            diff(left: $left, right: $right) {
                left {
                    number
                }
                right {
                    number
                }
                items {
                    item
                    status
                }
            }
        }"""
        variables = {
            "left": {"name": "bogus", "number": 1},
            "right": {"name": right_bm.name, "number": right_bm.number},
        }
        result = execute(query, variables=variables)

        # Then None is returned
        assert_data(self, result, {"diff": None})

    def test_should_return_none_when_right_does_not_exist(self):
        left_bm = self.left_bm

        query = """query Diff($left: BuildInput!, $right: BuildInput!) {
            diff(left: $left, right: $right) {
                left {
                    number
                }
                right {
                    number
                }
                items {
                    item
                    status
                }
            }
        }"""
        variables = {
            "left": {"name": left_bm.name, "number": left_bm.number},
            "right": {"name": "bogus", "number": 1},
        }
        result = execute(query, variables=variables)

        # Then None is returned
        assert_data(self, result, {"diff": None})


class MachinesQueryTestCase(TestCase):
    """Tests for the machines query"""

    maxDiff = None

    def test(self):
        babette_builds = BuildManFactory.create_batch(
            3, build_attr__build_model__name="babette"
        )
        BuildManFactory.create_batch(3, build_attr__build_model__name="lighthouse")

        # publish a build
        buildman = babette_builds[-1]
        buildman.publish()

        query = """{
            machines {
                name
                builds
                latestBuild {
                    name
                }
                publishedBuild {
                    number
                }
            }
        }"""

        result = execute(query)

        expected = [
            {
                "name": "babette",
                "builds": 3,
                "latestBuild": {"name": "babette"},
                "publishedBuild": {"number": buildman.number},
            },
            {
                "name": "lighthouse",
                "builds": 3,
                "latestBuild": {"name": "lighthouse"},
                "publishedBuild": None,
            },
        ]
        assert_data(self, result, {"machines": expected})

    def test_only_name(self):
        # basically test that only selecting the bame doesn't query other infos
        # (coverage.py)
        BuildManFactory.create_batch(2, build_attr__build_model__name="babette")
        BuildManFactory.create_batch(3, build_attr__build_model__name="lighthouse")
        query = """{
            machines {
                name
            }
        }"""
        result = execute(query)

        assert_data(
            self, result, {"machines": [{"name": "babette"}, {"name": "lighthouse"}]}
        )


class PackagesQueryTestCase(TestCase):
    """Tests for the packages query"""

    maxDiff = None

    def test(self):
        # given the pulled build with packages
        build = BuildManFactory.create()
        build.pull()

        # when we query the build's packages
        query = """query Packages($name: String!, $number: Int!) {
            packages(name: $name, number: $number)
        }"""
        result = execute(query, {"name": build.name, "number": build.number})

        # Then we get the list of packages in the build
        assert_data(self, result, {"packages": PACKAGE_INDEX})

    def test_when_not_pulled_returns_none(self):
        # given the unpulled package
        build = BuildManFactory.create()

        # when we query the build's packages
        query = """query Packages($name: String!, $number: Int!) {
            packages(name: $name, number: $number)
        }"""
        result = execute(query, {"name": build.name, "number": build.number})

        # Then none is returned
        assert_data(self, result, {"packages": None})

    def test_should_return_none_when_package_index_missing(self):
        # given the pulled build with index file missing
        build = BuildManFactory.create()
        build.pull()
        (build.storage_build.get_path(Content.BINPKGS) / "Packages").unlink()

        # when we query the build's packages
        query = """query Packages($name: String!, $number: Int!) {
            packages(name: $name, number: $number)
        }"""
        result = execute(query, {"name": build.name, "number": build.number})

        # Then none is returned
        assert_data(self, result, {"packages": None})


class PublishMutationTestCase(TestCase):
    """Tests for the publish mutation"""

    def test_publish_when_pulled(self):
        """Should publish builds"""
        build = BuildManFactory.create()
        build.pull()
        query = """mutation Publish($name: String!, $number: Int!) {
            publish(name: $name, number: $number) {
                publishedBuild {
                    number
                }
            }
        }"""
        result = execute(query, variables={"name": build.name, "number": build.number})

        assert_data(
            self, result, {"publish": {"publishedBuild": {"number": build.number}}}
        )

    def test_publish_when_not_pulled(self):  # pylint: disable=no-self-use
        """Should publish builds"""
        query = """mutation {
            publish(name: "babette", number: 193) {
                publishedBuild {
                    number
                }
            }
        }"""
        with mock.patch(
            "gentoo_build_publisher.graphql.publish_build.delay"
        ) as publish_delay:
            execute(query)

        publish_delay.assert_called_once_with("babette", 193)


class ScheduleBuildMutationTestCase(TestCase):
    """Tests for the build mutation"""

    maxDiff = None

    def test(self):
        query = 'mutation { scheduleBuild(name: "babette") }'
        schedule_build_path = "gentoo_build_publisher.graphql.schedule_build"
        with mock.patch(schedule_build_path) as mock_schedule_build:
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
        query = 'mutation { scheduleBuild(name: "babette") }'
        schedule_build_path = "gentoo_build_publisher.graphql.schedule_build"
        with mock.patch(schedule_build_path) as mock_schedule_build:
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