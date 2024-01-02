"""Jenkins api for Gentoo Build Publisher"""
from __future__ import annotations

import json as jsonlib
import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import PurePosixPath
from typing import Any, TypeVar

import requests
from yarl import URL

from gentoo_build_publisher.common import Build
from gentoo_build_publisher.settings import JENKINS_DEFAULT_CHUNK_SIZE, Settings
from gentoo_build_publisher.utils import read_package_file

AuthTuple = tuple[str, str]
logger = logging.getLogger(__name__)

COPY_ARTIFACT_PLUGIN = "copyartifact@1.47"
CREATE_BUILD_XML = read_package_file("create_machine_job.xml")
CREATE_REPO_XML = read_package_file("create_repo_job.xml")
FOLDER_XML = read_package_file("folder.xml")
PATH_SEPARATOR = "/"
HTTP_NOT_FOUND = 404
XML_PATHS = {
    "BRANCH_NAME": "scm/branches/hudson.plugins.git.BranchSpec/name",
    "SCM_URL": "scm/userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url",
}

_T = TypeVar("_T", bound="JenkinsConfig")


@dataclass(frozen=True, slots=True)
class JenkinsConfig:
    """Configuration for JenkinsBuild"""

    base_url: URL
    user: str | None = None
    api_key: str | None = None
    artifact_name: str = "build.tar.gz"
    download_chunk_size: int = JENKINS_DEFAULT_CHUNK_SIZE
    requests_timeout: int = 10  # seconds

    @classmethod
    def from_settings(cls: type[_T], settings: Settings) -> _T:
        """Return config given settings"""
        return cls(
            base_url=URL(settings.JENKINS_BASE_URL),
            user=settings.JENKINS_USER,
            artifact_name=settings.JENKINS_ARTIFACT_NAME,
            api_key=settings.JENKINS_API_KEY,
            download_chunk_size=settings.JENKINS_DOWNLOAD_CHUNK_SIZE,
        )

    def auth(self) -> AuthTuple | None:
        """The auth used for requests

        Either a 2-tuple or `None`
        """
        if self.user is None or self.api_key is None:
            return None

        return (self.user, self.api_key)


@dataclass(frozen=True, slots=True)
class JenkinsMetadata:
    """data structure for Jenkins build

    Comes from the Jenkins API, e.g. http://jenkins/job/babette/123/api/json
    """

    duration: int
    timestamp: int  # Jenkins timestamps are in milliseconds


class ProjectPath(PurePosixPath):
    """Jenkins has the concept of "project paths" that are not the same as the Jenkins
    URL path so we need something that can manipulate and convert between the two.  For
    example the project path may be "Gentoo/repos/gentoo" but the URL path would be
    "/job/Gentoo/job/repos/job/gentoo".

    ProjectPaths are always absolute.
    """

    def __new__(cls, *args: Any) -> ProjectPath:
        if not (args and str(args[0]).startswith(PATH_SEPARATOR)):
            args = (PATH_SEPARATOR, *args)

        return super().__new__(cls, *args)

    @property
    def url_path(self) -> str:
        """Convert project path to an absolute URL path"""
        return PATH_SEPARATOR.join(
            i for part in self.parts for i in ["job", part] if part != PATH_SEPARATOR
        )

    def __str__(self) -> str:
        return super().__str__().strip(PATH_SEPARATOR).lstrip(".")


class URLBuilder:
    """We build Jenkins build URLs 👷

    This is an object that stores url builders for builds in Jenkins. You use it
    something like this:

        >>> builder = URLBuilder(jenkins_config)
        >>> build_url = builder.build(my_build)
        >>> build_logs_url = builder.logs(my_build)
    """

    formatters: dict[str, str] = {
        "artifact": "job/{arg.machine}/{arg.build_id}/artifact/{config.artifact_name}",
        "build": "job/{arg.machine}/{arg.build_id}",
        "build_scheduler": "job/{arg}/build",
        "logs": "job/{arg.machine}/{arg.build_id}/consoleText",
        "metadata": "job/{arg.machine}/{arg.build_id}/api/json",
        "job": "job/{arg}/api/json",
    }
    """Format strings using "build" and "config" arguments"""

    def __init__(self, config: JenkinsConfig):
        self.config = config

    def __getattr__(self, name: str) -> Any:
        try:
            return partial(self.builder, self.formatters[name])
        except KeyError as error:
            raise AttributeError(repr(name)) from error

    def builder(self, formatter: str, arg: Any) -> URL:
        """Given the parts, and build, build a URL"""
        return self.config.base_url / formatter.format(config=self.config, arg=arg)

    def get_builders(self) -> list[str]:
        """Return the names of all the builders

        Not names like "Bob" but names like "logs"
        """
        return [*self.formatters]


class Jenkins:
    """Interface to Jenkins"""

    def __init__(self, config: JenkinsConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.auth = config.auth()
        self.timeout = config.requests_timeout
        self.url = URLBuilder(config)

    @property
    def project_root(self) -> ProjectPath:
        """Return the ProjectPath of the base_url"""
        url_path = self.config.base_url.path

        return ProjectPath(
            PATH_SEPARATOR.join(url_path.split(f"{PATH_SEPARATOR}job{PATH_SEPARATOR}"))
        )

    def download_artifact(self, build: Build) -> Iterable[bytes]:
        """Download and yield the build artifact in chunks of bytes"""
        url = self.url.artifact(build)
        http_response = self.session.get(str(url), stream=True, timeout=self.timeout)
        http_response.raise_for_status()

        return http_response.iter_content(
            chunk_size=self.config.download_chunk_size, decode_unicode=False
        )

    def get_logs(self, build: Build) -> str:
        """Get and return the build's jenkins logs"""
        url = self.url.logs(build)
        http_response = self.session.get(str(url), timeout=self.timeout)
        http_response.raise_for_status()

        return http_response.text

    def get_metadata(self, build: Build) -> JenkinsMetadata:
        """Query Jenkins for build's metadata"""
        url = self.url.metadata(build)
        http_response = self.session.get(str(url), timeout=self.timeout)
        http_response.raise_for_status()

        json = http_response.json()

        return JenkinsMetadata(duration=json["duration"], timestamp=json["timestamp"])

    @classmethod
    def from_settings(cls: type[Jenkins], settings: Settings) -> Jenkins:
        """Return a JenkinsBuild instance given settings"""
        config = JenkinsConfig.from_settings(settings)
        return cls(config)

    def schedule_build(self, machine: str, **params: Any) -> str | None:
        """Schedule a build on Jenkins

        `params` are build parameters to pass to the job instead of the defaults.
        """
        url = self.url.build_scheduler(machine)
        build_params = self.get_job_parameters(machine)

        # parameter logic here is based on
        # https://stackoverflow.com/questions/20359810/how-to-trigger-jenkins-builds-remotely-and-to-pass-parameters
        build_params = build_params.copy()

        for key, value in params.items():
            if key in build_params:
                build_params[key] = value
            else:
                raise ValueError(f"{key} is not a valid parameter for this build")
        params_list = [
            {"name": key, "value": value} for key, value in build_params.items()
        ]
        json_params = jsonlib.dumps({"parameter": params_list})

        http_response = self.session.post(
            str(url), data={"json": json_params}, timeout=self.timeout
        )
        http_response.raise_for_status()

        # All that Jenkins gives us is the location of the queued request.  Let's return
        # that.
        return http_response.headers.get("location")

    def project_exists(self, project_path: ProjectPath) -> bool:
        """Return True iff project_path exists on the Jenkins instance"""
        return self.url_path_exists(project_path.url_path)

    def url_path_exists(self, url_path: str) -> bool:
        """Return True iff url_path exists on the Jenkins instance"""
        url = self.config.base_url.with_path(url_path)
        http_response = self.session.head(
            str(url), timeout=self.timeout, allow_redirects=True
        )

        if http_response.status_code == HTTP_NOT_FOUND:
            return False

        http_response.raise_for_status()

        return True

    def create_item(self, project_path: ProjectPath, xml: str) -> None:
        """Given the xml and project path create an item in Jenkins"""
        if self.project_exists(project_path):
            raise FileExistsError(project_path)

        parent_path = project_path.parent
        url = self.config.base_url.with_path(parent_path.url_path) / "createItem"
        params = {"name": project_path.name}
        headers = {"Content-Type": "text/xml"}

        http_response = self.session.post(
            str(url),
            data=xml,
            headers=headers,
            params=params,
            timeout=self.config.requests_timeout,
        )

        if http_response.status_code == HTTP_NOT_FOUND:
            raise FileNotFoundError(project_path.parent)

        http_response.raise_for_status()

    def get_item(self, project_path: ProjectPath) -> str:
        """Return the xml definition for the given project"""
        url = self.config.base_url.with_path(project_path.url_path) / "config.xml"

        http_response = self.session.get(str(url), timeout=self.config.requests_timeout)

        if http_response.status_code == HTTP_NOT_FOUND:
            raise FileNotFoundError(project_path.parent)

        http_response.raise_for_status()

        return http_response.text

    def get_job_parameters(self, machine: str) -> dict[str, Any]:
        """Return the parameters for the machine's job

        Each parameter is a dict of name -> default_value
        """
        url = self.url.job(machine)
        params = {
            "tree": "property[parameterDefinitions[name,defaultParameterValue[value]]]"
        }

        http_response = self.session.get(
            str(url), params=params, timeout=self.config.requests_timeout
        )
        http_response.raise_for_status()

        properties = http_response.json()["property"]
        props = [prop for prop in properties if "parameterDefinitions" in prop]

        if not props:
            return {}

        if len(props) != 1:
            raise ValueError("Unexpected number of parameterDefinitions", props)

        return {
            param["name"]: param["defaultParameterValue"]["value"]
            for param in props[0]["parameterDefinitions"]
        }

    def make_folder(
        self, project_path: ProjectPath, parents: bool = False, exist_ok: bool = False
    ) -> None:
        """Create a project folder with the given path"""
        if project_path == ProjectPath():
            # Cannot create the root
            self.maybe_raise_folderexists(project_path, exist_ok)
            return

        if parents and (parent := project_path.parent) != ProjectPath():
            self.make_folder(parent, parents=True, exist_ok=True)

        try:
            self.create_item(project_path, FOLDER_XML)
        except FileExistsError:
            self.maybe_raise_folderexists(project_path, exist_ok)

    def is_folder(self, project_path: ProjectPath) -> bool:
        """Return True if project_path is a folder"""
        if project_path == ProjectPath():
            return True
        try:
            xml = self.get_item(project_path)
        except FileNotFoundError:
            return False

        tree = ET.fromstring(xml)

        return tree.tag == "com.cloudbees.hudson.plugins.folder.Folder"

    def maybe_raise_folderexists(self, folder: ProjectPath, exist_ok: bool) -> None:
        """Maybe raise FileExistsError"""
        if not exist_ok or not self.is_folder(folder):
            raise FileExistsError(folder)

    def install_plugin(self, plugin: str) -> None:
        """Ensure the given plugin is installed.

        Jenkins uses name@version syntax for `plugin`, for example "copyartifact@1.47"
        """
        url = self.config.base_url.with_path("/pluginManager/installNecessaryPlugins")
        http_response = self.session.post(
            str(url),
            headers={"Content-Type": "text/xml"},
            data=f'<jenkins><install plugin="{plugin}" /></jenkins>',
        )

        http_response.raise_for_status()

    def create_repo_job(self, repo_name: str, repo_url: str, repo_branch: str) -> None:
        """Create a repo job in the "repos" folder

        Assumes that the "repos" folder exists under the project root.
        """
        repo_path = self.project_root / "repos" / repo_name

        self.create_item(repo_path, self.render_build_repo_xml(repo_url, repo_branch))

    def render_build_repo_xml(self, repo_url: str, repo_branch: str) -> str:
        """Return XML config for the given repo"""
        xml = ET.fromstring(CREATE_REPO_XML)

        branch = xml.find(XML_PATHS["BRANCH_NAME"])
        assert branch is not None
        branch.text = f"*/{repo_branch}"

        url = xml.find(XML_PATHS["SCM_URL"])
        assert url is not None
        url.text = repo_url

        return ET.tostring(xml).decode("UTF-8")

    def create_machine_job(
        self,
        machine_name: str,
        repo_url: str,
        repo_branch: str,
        ebuild_repos: list[str],
    ) -> None:
        """Create a machine job to build the given machine"""
        machine_path = self.project_root / machine_name

        self.install_plugin(COPY_ARTIFACT_PLUGIN)
        self.create_item(
            machine_path,
            self.render_build_machine_xml(repo_url, repo_branch, ebuild_repos),
        )

    def render_build_machine_xml(
        self, repo_url: str, repo_branch: str, ebuild_repos: list[str]
    ) -> str:
        """Return XML config for the given machine"""
        xml = ET.fromstring(CREATE_BUILD_XML)
        parts = [
            "properties",
            "org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty",
            "triggers",
            "jenkins.triggers.ReverseBuildTrigger/upstreamProjects",
        ]
        repos_path = PATH_SEPARATOR.join(parts)
        upstream_repos = xml.find(repos_path)
        assert upstream_repos is not None
        upstream_repos.text = ",".join(f"repos/{repo}" for repo in ebuild_repos)

        url_path = (
            "definition/scm/userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url"
        )
        url = xml.find(url_path)
        assert url is not None
        url.text = repo_url

        branch_path = "definition/scm/branches/hudson.plugins.git.BranchSpec/name"
        branch_name = xml.find(branch_path)
        assert branch_name is not None
        branch_name.text = f"*/{repo_branch}"

        return ET.tostring(xml).decode("UTF-8")
