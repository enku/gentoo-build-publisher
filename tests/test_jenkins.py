"""Tests for the Jenkins interface"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import dataclasses as dc
import io
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import requests
from yarl import URL

from gentoo_build_publisher.jenkins import (
    COPY_ARTIFACT_PLUGIN,
    Jenkins,
    JenkinsConfig,
    JenkinsMetadata,
    ProjectPath,
    URLBuilder,
    xml,
)
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import Build, EbuildRepo, MachineJob, Repo

from . import JENKINS_CONFIG
from . import BaseTestCase as TestCase
from . import MockJenkins, test_data
from .setup_types import Fixtures, SetupContext, SetupOptions

JOB_PARAMS = json.loads(test_data("job_parameters.json"))


class JenkinsTestCase(TestCase):
    """Tests for the Jenkins api wrapper"""

    def test_download_artifact(self) -> None:
        """.download_artifact should download the given build artifact"""
        # Given the build id
        build = Build("babette", "193")

        # Given the Jenkins instance
        jenkins = MockJenkins(JENKINS_CONFIG)

        # When we call download_artifact on the build
        stream = jenkins.download_artifact(build)

        # Then it streams the build artifact's contents
        bytes_io = io.BytesIO()
        for chunk in stream:
            bytes_io.write(chunk)

        jenkins.mock_get.assert_called_with(
            "https://jenkins.invalid/job/babette/193/artifact/build.tar.gz", stream=True
        )

    def test_download_artifact_with_no_auth(self) -> None:
        # Given the build id
        build = Build("babette", "193")

        # Given the Jenkins instance having no user/api_key
        jenkins = MockJenkins(JENKINS_CONFIG)

        # When we call download_artifact on the build
        jenkins.download_artifact(build)

        # Then it requests the artifact with no auth
        jenkins.mock_get.assert_called_with(
            "https://jenkins.invalid/job/babette/193/artifact/build.tar.gz", stream=True
        )

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_from_settings(self) -> None:
        """.from_settings() should return an instance instantiated from settings"""
        # Given the settings
        settings = Settings(
            JENKINS_BASE_URL="https://foo.bar.invalid/jenkins",
            JENKINS_API_KEY="super secret key",
            JENKINS_USER="admin",
            JENKINS_ARTIFACT_NAME="stuff.tar",
            STORAGE_PATH=Path("/dev/null"),
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

    def test_get_metadata(self) -> None:
        mock_response = test_data("jenkins_build.json")
        build = Build("babette", "291")
        jenkins = Jenkins(JENKINS_CONFIG)

        with mock.patch.object(jenkins.session, "get") as mock_requests_get:
            mock_requests_get.return_value.json.return_value = json.loads(mock_response)
            metadata = jenkins.get_metadata(build)

        self.assertEqual(
            metadata, JenkinsMetadata(duration=3892427, timestamp=1635811517838)
        )
        mock_requests_get.assert_called_once_with(
            "https://jenkins.invalid/job/babette/291/api/json"
        )
        mock_requests_get.return_value.json.assert_called_once_with()

    def test_project_root_typical_setting(self) -> None:
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid/job/Gentoo"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath("Gentoo"))

    def test_project_root_typical_setting_with_trailing_slash(self) -> None:
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid/job/Gentoo/"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath("Gentoo"))

    def test_project_root_from_url_root(self) -> None:
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid/"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath(""))

    def test_project_root_from_url_root_with_no_trailing_slash(self) -> None:
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath(""))

    def test_project_root_deeply_nested(self) -> None:
        jenkins_config = JenkinsConfig(
            base_url=URL("https://jenkins.invalid/job/foo/job/bar/job/baz"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )
        jenkins = Jenkins(jenkins_config)

        self.assertEqual(jenkins.project_root, ProjectPath("foo/bar/baz"))

    def test_project_root_bogus_jenkins_base(self) -> None:
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
    def test_should_return_false_when_does_not_exist(self) -> None:
        def mock_head(url: str, *args: Any, **kwargs: Any) -> requests.Response:
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

    def test_should_return_true_when_exists(self) -> None:
        def mock_head(url: str, *args: Any, **kwargs: Any) -> requests.Response:
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

    def test_should_return_true_when_error_response(self) -> None:
        def mock_head(_url: str, *args: Any, **kwargs: Any) -> requests.Response:
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

    def test_creates_item(self) -> None:
        xml_str = "<jenkins>test</jenkins>"
        project_path = ProjectPath("TestItem")
        jenkins = MockJenkins(JENKINS_CONFIG)

        jenkins.create_item(project_path, xml_str)

        self.assertEqual(jenkins.root.get(["TestItem"]), "<jenkins>test</jenkins>")
        self.assertEqual(jenkins.session.auth(), ("jenkins", "foo"))
        jenkins.session.post.assert_called_once_with(
            "https://jenkins.invalid/createItem",
            data="<jenkins>test</jenkins>",
            headers={"Content-Type": "text/xml"},
            params={"name": "TestItem"},
        )

    def test_when_parent_folder_does_not_exist(self) -> None:
        xml_str = "<jenkins>test</jenkins>"
        project_path = ProjectPath("Gentoo/TestItem")
        jenkins = MockJenkins(JENKINS_CONFIG)

        with self.assertRaises(FileNotFoundError) as context:
            jenkins.create_item(project_path, xml_str)

        exception = context.exception
        self.assertEqual(exception.args, (project_path.parent,))
        jenkins.session.post.assert_called_once_with(
            "https://jenkins.invalid/job/Gentoo/createItem",
            data="<jenkins>test</jenkins>",
            headers={"Content-Type": "text/xml"},
            params={"name": "TestItem"},
        )

    def test_when_parent_folder_does_exist(self) -> None:
        xml_str = "<jenkins>test</jenkins>"
        project_path = ProjectPath("Gentoo/TestItem")
        jenkins = MockJenkins(JENKINS_CONFIG)

        # Create parent
        jenkins.root.set(["Gentoo"], None)

        jenkins.create_item(project_path, xml_str)

        self.assertEqual(
            jenkins.root.get(["Gentoo", "TestItem"]), "<jenkins>test</jenkins>"
        )
        jenkins.session.post.assert_called_once_with(
            "https://jenkins.invalid/job/Gentoo/createItem",
            data="<jenkins>test</jenkins>",
            headers={"Content-Type": "text/xml"},
            params={"name": "TestItem"},
        )

    def test_raises_exception_on_http_errors(self) -> None:
        xml_str = "<jenkins>test</jenkins>"
        project_path = ProjectPath("TestItem")
        jenkins = MockJenkins(JENKINS_CONFIG)

        with mock.patch.object(jenkins.session, "post") as mock_post:
            response_400 = requests.Response()
            response_400.status_code = 400
            mock_post.return_value = response_400

            with self.assertRaises(requests.exceptions.HTTPError):
                jenkins.create_item(project_path, xml_str)

        mock_post.assert_called_once_with(
            "https://jenkins.invalid/createItem",
            data="<jenkins>test</jenkins>",
            headers={"Content-Type": "text/xml"},
            params={"name": "TestItem"},
        )


class GetItemTestCase(TestCase):
    def test_gets_item(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        jenkins.root.set(["Gentoo"], "<jenkins>Test</jenkins>")
        project_path = ProjectPath("Gentoo")

        self.assertEqual(jenkins.get_item(project_path), "<jenkins>Test</jenkins>")

        jenkins.session.get.assert_called_once_with(
            "https://jenkins.invalid/job/Gentoo/config.xml"
        )

    def test_raises_exception_on_http_errors(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        project_path = ProjectPath("Gentoo")

        with mock.patch.object(jenkins.session, "get") as mock_get:
            response_400 = requests.Response()
            response_400.status_code = 400
            mock_get.return_value = response_400

            with self.assertRaises(requests.exceptions.HTTPError):
                jenkins.get_item(project_path)

        mock_get.assert_called_once_with(
            "https://jenkins.invalid/job/Gentoo/config.xml"
        )


class MakeFolderTestCase(TestCase):
    """Tests for the Jenkins.make_folder method"""

    def test_when_folder_does_not_exist_creates_folder(self) -> None:
        project_path = ProjectPath("Gentoo")
        jenkins = MockJenkins(JENKINS_CONFIG)

        jenkins.make_folder(project_path)

        self.assertEqual(jenkins.root.get(["Gentoo"]), xml.FOLDER)

    def test_when_folder_already_exists(self) -> None:
        project_path = ProjectPath("Gentoo")
        jenkins = MockJenkins(JENKINS_CONFIG)

        jenkins.root.set(["Gentoo"], xml.FOLDER)

        with self.assertRaises(FileExistsError):
            jenkins.make_folder(project_path)

    def test_when_item_exists_but_is_not_a_folder(self) -> None:
        project_path = ProjectPath("Gentoo")
        jenkins = MockJenkins(JENKINS_CONFIG)

        jenkins.root.set(["Gentoo"], "<jenkins>Test</jenkins>")

        with self.assertRaises(FileExistsError):
            jenkins.make_folder(project_path)

    def test_when_folder_already_exists_exist_ok_true(self) -> None:
        project_path = ProjectPath("Gentoo")
        jenkins = MockJenkins(JENKINS_CONFIG)

        jenkins.root.set(["Gentoo"], xml.FOLDER)
        jenkins.make_folder(project_path, exist_ok=True)

    def test_when_parent_folder_does_not_exist(self) -> None:
        project_path = ProjectPath("Gentoo/repos")
        jenkins = MockJenkins(JENKINS_CONFIG)

        with self.assertRaises(FileNotFoundError):
            jenkins.make_folder(project_path)

    def test_when_parent_folder_does_not_exist_and_parents_true(self) -> None:
        project_path = ProjectPath("Gentoo/repos")
        jenkins = MockJenkins(JENKINS_CONFIG)

        jenkins.make_folder(project_path, parents=True)

        self.assertEqual(jenkins.root.get(["Gentoo"]), xml.FOLDER)
        self.assertEqual(jenkins.root.get(["Gentoo", "repos"]), xml.FOLDER)

    def test_when_passing_root_and_not_exists_ok_returns_error(self) -> None:
        project_path = ProjectPath()
        jenkins = MockJenkins(JENKINS_CONFIG)

        with self.assertRaises(FileExistsError):
            jenkins.make_folder(project_path)

    def test_when_passing_root_and_exists_ok_succeeds(self) -> None:
        project_path = ProjectPath()
        jenkins = MockJenkins(JENKINS_CONFIG)

        jenkins.make_folder(project_path, exist_ok=True)


class IsFolderTestCase(TestCase):
    """Tests for the Jenkins.is_folder method"""

    def test_when_is_a_folder_returns_true(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        project_path = ProjectPath("Gentoo")
        jenkins.root.set(["Gentoo"], xml.FOLDER)

        self.assertEqual(jenkins.is_folder(project_path), True)

    def test_when_is_not_a_folder_returns_false(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        project_path = ProjectPath("Gentoo")
        jenkins.root.set(["Gentoo"], "<jenkins>Test</jenkins>")

        self.assertEqual(jenkins.is_folder(project_path), False)

    def test_when_does_not_exist_returns_false(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        project_path = ProjectPath("Gentoo")

        self.assertEqual(jenkins.is_folder(project_path), False)

    def test_root_folder(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        self.assertEqual(jenkins.is_folder(ProjectPath()), True)


class InstallPluginTestCase(TestCase):
    """Tests for the Jenkins.install_plugin method"""

    def test_installs_plugin(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)

        jenkins.install_plugin("copyartifact@1.47")

        jenkins.session.post.assert_called_once_with(
            "https://jenkins.invalid/pluginManager/installNecessaryPlugins",
            headers={"Content-Type": "text/xml"},
            data='<jenkins><install plugin="copyartifact@1.47" /></jenkins>',
        )


class CreateRepoJobTestCase(TestCase):
    """Tests for the Jenkins.create_repo_job method"""

    def test_creates_given_repo(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        jenkins.make_folder(ProjectPath("repos"))
        jenkins.session.post.reset_mock()

        repo = EbuildRepo(
            name="gentoo",
            url="https://github.com/gentoo-mirror/gentoo.git",
            branch="master",
        )

        jenkins.create_repo_job(repo)

        jenkins.session.post.assert_called_once_with(
            "https://jenkins.invalid/job/repos/createItem",
            data=xml.build_repo(repo),
            headers={"Content-Type": "text/xml"},
            params={"name": "gentoo"},
        )

    def test_when_base_url_is_not_root(self) -> None:
        config = dc.replace(
            JENKINS_CONFIG, base_url=URL("https://jenkins.invalid/job/Gentoo")
        )
        jenkins = MockJenkins(config)
        jenkins.make_folder(ProjectPath("Gentoo/repos"), parents=True)
        jenkins.session.post.reset_mock()

        repo = EbuildRepo(
            name="gentoo",
            url="https://anongit.gentoo.org/git/repo/gentoo.git",
            branch="feature",
        )

        jenkins.create_repo_job(repo)

        jenkins.session.post.assert_called_once_with(
            "https://jenkins.invalid/job/Gentoo/job/repos/createItem",
            data=xml.build_repo(repo),
            headers={"Content-Type": "text/xml"},
            params={"name": "gentoo"},
        )


class CreateMachineJobTestCase(TestCase):
    """Tests for the Jenkins.create_machine_job method"""

    def test_creates_given_machine(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        jenkins.session.post.reset_mock()

        job = MachineJob(
            name="base",
            repo=Repo(
                url="https://github.com/enku/gbp-machines.git",
                branch="master",
            ),
            ebuild_repos=["gentoo"],
        )

        jenkins.create_machine_job(job)

        jenkins.session.post.assert_has_calls(
            [
                mock.call(
                    "https://jenkins.invalid/pluginManager/installNecessaryPlugins",
                    headers={"Content-Type": "text/xml"},
                    data=f'<jenkins><install plugin="{COPY_ARTIFACT_PLUGIN}" /></jenkins>',
                ),
                mock.call(
                    "https://jenkins.invalid/createItem",
                    data=xml.build_machine(job),
                    headers={"Content-Type": "text/xml"},
                    params={"name": "base"},
                ),
            ]
        )


class ProjectPathTestCase(TestCase):
    """Tests for the ProjectPath class"""

    def test_job_path_with_root(self) -> None:
        project_path = ProjectPath("/")

        self.assertEqual(project_path.url_path, "")

    def test_job_path_from_empty_path(self) -> None:
        project_path = ProjectPath()

        self.assertEqual(project_path.url_path, "")

    def test_job_path_deeply_nested(self) -> None:
        project_path = ProjectPath("/foo/bar/baz")

        self.assertEqual(project_path.url_path, "job/foo/job/bar/job/baz")

    def test_job_path_with_job_in_the_path(self) -> None:
        project_path = ProjectPath("Gentoo/job/job")

        self.assertEqual(project_path.url_path, "job/Gentoo/job/job/job/job")

    def test_str(self) -> None:
        project_path = ProjectPath("/Gentoo/repos/marduk/")

        self.assertEqual(str(project_path), "Gentoo/repos/marduk")


@contextmanager
def mock_jenkins(_options: SetupOptions, _fixtures: Fixtures) -> SetupContext[Jenkins]:
    obj = Jenkins(JENKINS_CONFIG)
    with mock.patch.object(
        obj.session, "get", **{"return_value.json.return_value": JOB_PARAMS}
    ):
        yield obj


class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    requires = [mock_jenkins]

    def test(self) -> None:
        jenkins = self.fixtures.mock_jenkins

        with mock.patch.object(jenkins.session, "post") as mock_post:
            mock_response = mock_post.return_value
            attrs = {
                "status_code": 301,
                "headers": {"location": "https://jenkins.invalid/queue/item/31528/"},
            }
            mock_response.configure_mock(**attrs)
            location = jenkins.schedule_build("babette", BUILD_TARGET="emptytree")

        self.assertEqual(location, "https://jenkins.invalid/queue/item/31528/")
        jenkins.session.get.assert_called_once_with(  # pylint: disable=no-member
            "https://jenkins.invalid/job/babette/api/json",
            params={
                "tree": "property[parameterDefinitions[name,defaultParameterValue[value]]]"
            },
        )
        mock_post.assert_called_once_with(
            "https://jenkins.invalid/job/babette/build",
            data={
                "json": '{"parameter": [{"name": "BUILD_TARGET", "value": "emptytree"}]}'
            },
        )

    def test_schedule_build_with_bogus_build_params(self) -> None:
        with self.assertRaises(ValueError) as context:
            self.fixtures.mock_jenkins.schedule_build(
                "babette", BOGUS="idunno", FOO="bar"
            )

        self.assertEqual(
            context.exception.args,
            ("parameter(s) ['BOGUS', 'FOO'] are invalid for this build",),
        )

    def test_should_raise_on_http_error(self) -> None:
        jenkins = self.fixtures.mock_jenkins

        class MyException(Exception):
            pass

        with mock.patch.object(jenkins.session, "post") as mock_post:
            mock_response = mock_post.return_value
            mock_response.raise_for_status.side_effect = MyException

            with self.assertRaises(MyException):
                jenkins.schedule_build("babette")

    def test_with_missing_location_header(self) -> None:
        # Sometimes the Jenkins response is missing the location header(?)
        jenkins = self.fixtures.mock_jenkins

        with mock.patch.object(jenkins.session, "post") as mock_post:
            attrs = {"status_code": 301, "headers": {}}
            mock_post.return_value.configure_mock(**attrs)
            location = jenkins.schedule_build("babette", BUILD_TARGET="world")

        self.assertEqual(location, None)


class GetJobParametersTests(TestCase):
    # pylint: disable=no-member
    def test_gets_parameter_name_and_default_values(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        mock_response = jenkins.session.response(200, test_data("job_parameters.json"))
        jenkins.session.mock_response("GET", "/job/babette/api/json", mock_response)

        response = jenkins.get_job_parameters("babette")

        self.assertEqual(response, {"BUILD_TARGET": "world"})

        jenkins.session.get.assert_called_once_with(
            "https://jenkins.invalid/job/babette/api/json",
            params={
                "tree": "property[parameterDefinitions[name,defaultParameterValue[value]]]"
            },
        )

    def test_returns_empty_if_no_paramdefs(self) -> None:
        jenkins = MockJenkins(JENKINS_CONFIG)
        mock_response = jenkins.session.response(
            200, json.dumps({"property": []}).encode()
        )
        jenkins.session.mock_response("GET", "/job/babette/api/json", mock_response)

        response = jenkins.get_job_parameters("babette")

        self.assertEqual(response, {})


class URLBuilderTestCase(TestCase):
    """Tests for the URLBuilder"""

    config = JenkinsConfig(base_url=URL("https://jenkins.invalid"))
    builder = URLBuilder(config)
    build = Build("jenny", "8675309")

    def test_get_builders(self) -> None:
        builders = self.builder.get_builders()

        self.assertIsInstance(builders, list)
        self.assertIn("build", builders)

    def test_getattr_returns_a_builder_function(self) -> None:
        url = self.builder.artifact(self.build)
        self.assertEqual(
            url, URL("https://jenkins.invalid/job/jenny/8675309/artifact/build.tar.gz")
        )

    def test_getattr_raises_attribute_error(self) -> None:
        with self.assertRaises(AttributeError):
            self.builder.bogus  # pylint: disable=pointless-statement
