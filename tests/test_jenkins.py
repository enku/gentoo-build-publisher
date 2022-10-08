"""Tests for the Jenkins interface"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import io
import json
import os
from unittest import TestCase, mock

import requests
from yarl import URL

from gentoo_build_publisher.jenkins import (
    Jenkins,
    JenkinsConfig,
    JenkinsMetadata,
    ProjectPath,
)
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import Build

from . import MockJenkins, test_data

JENKINS_CONFIG = JenkinsConfig(
    base_url=URL("https://jenkins.invalid"),
    api_key="foo",
    user="jenkins",
    artifact_name="build.tar.gz",
)


class JenkinsTestCase(TestCase):
    """Tests for the Jenkins api wrapper"""

    def test_artifact_url(self):
        """.build_url() should return the url of the given build artifact"""
        # Given the build id
        build = Build("babette.193")

        # Given the Jenkins instance
        jenkins = Jenkins(JENKINS_CONFIG)

        # When we call .build_url
        build_url = jenkins.artifact_url(build)

        # Then we get the expected url
        self.assertEqual(
            build_url,
            URL("https://jenkins.invalid/job/babette/193/artifact/build.tar.gz"),
        )

    def test_download_artifact(self):
        """.download_artifact should download the given build artifact"""
        # Given the build id
        build = Build("babette.193")

        # Given the Jenkins instance
        jenkins = MockJenkins(JENKINS_CONFIG)

        # When we call download_artifact on the build
        stream = jenkins.download_artifact(build)

        # Then it streams the build artifact's contents
        bytes_io = io.BytesIO()
        for chunk in stream:
            bytes_io.write(chunk)

        jenkins.mock_get.assert_called_with(
            "https://jenkins.invalid/job/babette/193/artifact/build.tar.gz",
            stream=True,
            timeout=jenkins.config.requests_timeout,
        )

    def test_download_artifact_with_no_auth(self):
        # Given the build id
        build = Build("babette.193")

        # Given the Jenkins instance having no user/api_key
        jenkins = MockJenkins(JENKINS_CONFIG)

        # When we call download_artifact on the build
        jenkins.download_artifact(build)

        # Then it requests the artifact with no auth
        jenkins.mock_get.assert_called_with(
            "https://jenkins.invalid/job/babette/193/artifact/build.tar.gz",
            stream=True,
            timeout=jenkins.config.requests_timeout,
        )

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_from_settings(self):
        """.from_settings() should return an instance instantiated from settings"""
        # Given the settings
        settings = Settings(
            JENKINS_BASE_URL="https://foo.bar.invalid/jenkins",
            JENKINS_API_KEY="super secret key",
            JENKINS_USER="admin",
            JENKINS_ARTIFACT_NAME="stuff.tar",
            STORAGE_PATH="/dev/null",
        )

        # When we instantiate Jenkins.from_settings
        jenkins = Jenkins.from_settings(settings)

        # Then we get a Jenkins instance with attributes from my_settings
        self.assertIsInstance(jenkins, Jenkins)
        self.assertEqual(
            jenkins.config.base_url, URL("https://foo.bar.invalid/jenkins")
        )
        self.assertEqual(jenkins.config.api_key, "super secret key")
        self.assertEqual(jenkins.config.user, "admin")
        self.assertEqual(jenkins.config.artifact_name, "stuff.tar")

    def test_get_metadata(self):
        mock_response = test_data("jenkins_build.json")
        build = Build("babette.291")
        jenkins = Jenkins(JENKINS_CONFIG)

        with mock.patch.object(jenkins.session, "get") as mock_requests_get:
            mock_requests_get.return_value.json.return_value = json.loads(mock_response)
            metadata = jenkins.get_metadata(build)

        self.assertEqual(
            metadata, JenkinsMetadata(duration=3892427, timestamp=1635811517838)
        )
        mock_requests_get.assert_called_once_with(
            "https://jenkins.invalid/job/babette/291/api/json",
            timeout=jenkins.config.requests_timeout,
        )
        mock_requests_get.return_value.json.assert_called_once_with()

    def test_project_root_typical_setting(self):
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid/job/Gentoo"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath("Gentoo"))

    def test_project_root_typical_setting_with_trailing_slash(self):
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid/job/Gentoo/"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath("Gentoo"))

    def test_project_root_from_url_root(self):
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid/"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath(""))

    def test_project_root_from_url_root_with_no_trailing_slash(self):
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath(""))

    def test_project_root_deeply_nested(self):
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid/job/foo/job/bar/job/baz"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath("foo/bar/baz"))

    def test_project_root_bogus_jenkins_base(self):
        # If the base url isn't of the form /job/foo/job/bar/job baz (should?) we return
        # the original path
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid/i/think/this/is/invalid"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath("i/think/this/is/invalid"))


class ProjectPathExistsTestCase(TestCase):
    def test_should_return_false_when_does_not_exist(self):
        def mock_head(url, *args, **kwargs):
            status_code = 404
            if url == "https://jenkins.invalid/job/Gentoo/job/repos/job/marduk":
                status_code = 200

            response = requests.Response()
            response.status_code = status_code

            return response

        jenkins = Jenkins(JENKINS_CONFIG)
        project_path = ProjectPath("Gentoo/repos/marduk")

        with mock.patch.object(jenkins.session, "head", side_effect=mock_head):
            self.assertEqual(jenkins.project_exists(project_path), True)

    def test_should_return_true_when_exists(self):
        def mock_head(url, *args, **kwargs):
            status_code = 200
            if url == "https://jenkins.invalid/job/Gentoo/job/repos/job/marduk":
                status_code = 404

            response = requests.Response()
            response.status_code = status_code

            return response

        jenkins = Jenkins(JENKINS_CONFIG)

        project_path = ProjectPath("Gentoo/repos/marduk")

        with mock.patch.object(jenkins.session, "head", side_effect=mock_head):
            self.assertEqual(jenkins.project_exists(project_path), False)

    def test_should_return_true_when_error_response(self):
        def mock_head(_url, *args, **kwargs):
            response = requests.Response()
            response.status_code = 401
            response.reason = "Unauthorized"

            return response

        jenkins = Jenkins(JENKINS_CONFIG)

        project_path = ProjectPath("Gentoo/repos/marduk")

        with mock.patch.object(jenkins.session, "head", side_effect=mock_head):
            with self.assertRaises(requests.exceptions.HTTPError):
                jenkins.project_exists(project_path)


class CreateItemTestCase(TestCase):
    """Tests for the Jenkins.create_item method"""

    def test_creates_item(self):
        xml = "<jenkins>test</jenkins>"
        project_path = ProjectPath("TestItem")
        jenkins = MockJenkins(JENKINS_CONFIG)

        jenkins.create_item(project_path, xml)

        self.assertEqual(jenkins.root.get(["TestItem"]), "<jenkins>test</jenkins>")
        self.assertEqual(jenkins.session.auth(), ("jenkins", "foo"))
        jenkins.session.post.assert_called_once_with(
            "https://jenkins.invalid/createItem",
            data="<jenkins>test</jenkins>",
            headers={"Content-Type": "text/xml"},
            params={"name": "TestItem"},
            timeout=10,
        )

    def test_when_parent_folder_does_not_exist(self):
        xml = "<jenkins>test</jenkins>"
        project_path = ProjectPath("Gentoo/TestItem")
        jenkins = MockJenkins(JENKINS_CONFIG)

        with self.assertRaises(FileNotFoundError) as context:
            jenkins.create_item(project_path, xml)

        exception = context.exception
        self.assertEqual(exception.args, (project_path.parent,))
        jenkins.session.post.assert_called_once_with(
            "https://jenkins.invalid/job/Gentoo/createItem",
            data="<jenkins>test</jenkins>",
            headers={"Content-Type": "text/xml"},
            params={"name": "TestItem"},
            timeout=10,
        )

    def test_when_parent_folder_does_exist(self):
        xml = "<jenkins>test</jenkins>"
        project_path = ProjectPath("Gentoo/TestItem")
        jenkins = MockJenkins(JENKINS_CONFIG)

        # Create parent
        jenkins.root.set(["Gentoo"], None)

        jenkins.create_item(project_path, xml)

        self.assertEqual(
            jenkins.root.get(["Gentoo", "TestItem"]), "<jenkins>test</jenkins>"
        )
        jenkins.session.post.assert_called_once_with(
            "https://jenkins.invalid/job/Gentoo/createItem",
            data="<jenkins>test</jenkins>",
            headers={"Content-Type": "text/xml"},
            params={"name": "TestItem"},
            timeout=10,
        )

    def test_raises_exception_on_http_errors(self):
        xml = "<jenkins>test</jenkins>"
        project_path = ProjectPath("TestItem")
        jenkins = MockJenkins(JENKINS_CONFIG)

        with mock.patch.object(jenkins.session, "post") as mock_post:
            response_400 = requests.Response()
            response_400.status_code = 400
            mock_post.return_value = response_400

            with self.assertRaises(requests.exceptions.HTTPError):
                jenkins.create_item(project_path, xml)

        mock_post.assert_called_once_with(
            "https://jenkins.invalid/createItem",
            data="<jenkins>test</jenkins>",
            headers={"Content-Type": "text/xml"},
            params={"name": "TestItem"},
            timeout=10,
        )


class ProjectPathTestCase(TestCase):
    """Tests for the ProjectPath class"""

    def test_job_path_with_root(self):
        project_path = ProjectPath("/")

        self.assertEqual(project_path.url_path, "")

    def test_job_path_from_empty_path(self):
        project_path = ProjectPath()

        self.assertEqual(project_path.url_path, "")

    def test_job_path_deeply_nested(self):
        project_path = ProjectPath("/foo/bar/baz")

        self.assertEqual(project_path.url_path, "job/foo/job/bar/job/baz")

    def test_job_path_with_job_in_the_path(self):
        project_path = ProjectPath("Gentoo/job/job")

        self.assertEqual(project_path.url_path, "job/Gentoo/job/job/job/job")

    def test_str(self):
        project_path = ProjectPath("/Gentoo/repos/marduk/")

        self.assertEqual(str(project_path), "Gentoo/repos/marduk")


class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self):
        name = "babette"
        settings = Settings(
            JENKINS_BASE_URL="https://jenkins.invalid",
            JENKINS_API_KEY="super secret key",
            JENKINS_USER="admin",
            STORAGE_PATH="/dev/null",
        )
        jenkins = Jenkins.from_settings(settings)

        with mock.patch.object(jenkins.session, "post") as mock_post:
            mock_response = mock_post.return_value
            mock_response.status_code = 401
            mock_response.headers = {
                "location": "https://jenkins.invalid/queue/item/31528/"
            }
            location = jenkins.schedule_build(name)

        self.assertEqual(location, "https://jenkins.invalid/queue/item/31528/")
        mock_post.assert_called_once_with(
            "https://jenkins.invalid/job/babette/build",
            timeout=jenkins.config.requests_timeout,
        )

    def test_should_raise_on_http_error(self):
        name = "babette"
        settings = Settings(
            JENKINS_BASE_URL="https://jenkins.invalid",
            JENKINS_API_KEY="super secret key",
            JENKINS_USER="admin",
            STORAGE_PATH="/dev/null",
        )
        jenkins = Jenkins.from_settings(settings)

        class MyException(Exception):
            pass

        with mock.patch.object(jenkins.session, "post") as mock_post:
            mock_response = mock_post.return_value
            mock_response.raise_for_status.side_effect = MyException

            with self.assertRaises(MyException):
                jenkins.schedule_build(name)
