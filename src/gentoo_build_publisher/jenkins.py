"""Jenkins api for Gentoo Build Publisher"""
from __future__ import annotations

import importlib.resources
import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Optional, Type, TypeVar

import requests
from dataclasses_json import dataclass_json
from yarl import URL

from gentoo_build_publisher.settings import JENKINS_DEFAULT_CHUNK_SIZE, Settings
from gentoo_build_publisher.types import Build

AuthTuple = tuple[str, str]
logger = logging.getLogger(__name__)

COPY_ARTIFACT_PLUGIN = "copyartifact@1.47"
CREATE_BUILD_XML = importlib.resources.read_text(
    "gentoo_build_publisher", "create_machine_job.xml", encoding="UTF-8"
)
CREATE_REPO_XML = importlib.resources.read_text(
    "gentoo_build_publisher", "create_repo_job.xml", encoding="UTF-8"
)
FOLDER_XML = importlib.resources.read_text(
    "gentoo_build_publisher", "folder.xml", encoding="UTF-8"
)

_T = TypeVar("_T", bound="JenkinsConfig")


@dataclass
class JenkinsConfig:
    """Configuration for JenkinsBuild"""

    base_url: URL
    user: Optional[str] = None
    api_key: Optional[str] = None
    artifact_name: str = "build.tar.gz"
    download_chunk_size: int = JENKINS_DEFAULT_CHUNK_SIZE
    requests_timeout: int = 10  # seconds

    @classmethod
    def from_settings(cls: Type[_T], settings: Settings) -> _T:
        """Return config given settings"""
        return cls(
            base_url=URL(settings.JENKINS_BASE_URL),
            user=settings.JENKINS_USER,
            artifact_name=settings.JENKINS_ARTIFACT_NAME,
            api_key=settings.JENKINS_API_KEY,
            download_chunk_size=settings.JENKINS_DOWNLOAD_CHUNK_SIZE,
        )

    def auth(self) -> Optional[AuthTuple]:
        """The auth used for requests

        Either a 2-tuple or `None`
        """
        if self.user is None or self.api_key is None:
            return None

        return (self.user, self.api_key)


@dataclass_json
@dataclass
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
        if not (args and args[0].startswith("/")):
            args = ("/", *args)

        return super().__new__(cls, *args)

    @property
    def url_path(self) -> str:
        """Convert project path to an absolute URL path"""
        parts = []

        for part in self.parts:
            if part == "/":
                continue

            parts.extend(["job", part])

        return "/".join(parts)

    def __str__(self) -> str:
        return super().__str__().strip("/")


class Jenkins:
    """Interface to Jenkins"""

    def __init__(self, config: JenkinsConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.auth = config.auth()
        self.timeout = config.requests_timeout

    @property
    def project_root(self) -> ProjectPath:
        """Return the ProjectPath of the base_url"""
        url_path = self.config.base_url.path

        return ProjectPath("/".join(url_path.split("/job/")))

    def url(self, build: Build) -> URL:
        """Return the Jenkins url for the build"""
        return self.config.base_url / "job" / build.machine / build.build_id

    def artifact_url(self, build: Build) -> URL:
        """Return the artifact url for build"""
        return self.url(build) / "artifact" / self.config.artifact_name

    def logs_url(self, build: Build) -> URL:
        """Return the url for the build's console logs"""
        return self.url(build) / "consoleText"

    def download_artifact(self, build: Build) -> Iterable[bytes]:
        """Download and yield the build artifact in chunks of bytes"""
        url = self.artifact_url(build)
        response = self.session.get(str(url), stream=True, timeout=self.timeout)
        response.raise_for_status()

        return response.iter_content(
            chunk_size=self.config.download_chunk_size, decode_unicode=False
        )

    def get_logs(self, build: Build) -> str:
        """Get and return the build's jenkins logs"""
        url = self.logs_url(build)
        response = self.session.get(str(url), timeout=self.timeout)
        response.raise_for_status()

        return response.text

    def get_metadata(self, build: Build) -> JenkinsMetadata:
        """Query Jenkins for build's metadata"""
        url = self.url(build) / "api" / "json"
        response = self.session.get(str(url), timeout=self.timeout)
        response.raise_for_status()

        return JenkinsMetadata.from_dict(  # type: ignore  # pylint: disable=no-member
            response.json()
        )

    @classmethod
    def from_settings(cls: type[Jenkins], settings: Settings) -> Jenkins:
        """Return a JenkinsBuild instance given settings"""
        config = JenkinsConfig.from_settings(settings)
        return cls(config)

    def schedule_build(self, machine: str) -> str:
        """Schedule a build on Jenkins"""
        url = self.config.base_url / "job" / machine / "build"
        response = self.session.post(str(url), timeout=self.timeout)
        response.raise_for_status()

        # All that Jenkins gives us is the location of the queued request.  Let's return
        # that.
        return response.headers["location"]

    def project_exists(self, project_path: ProjectPath) -> bool:
        """Return True iff project_path exists on the Jenkins instance"""
        return self.url_path_exists(project_path.url_path)

    def url_path_exists(self, url_path: str) -> bool:
        """Return True iff url_path exists on the Jenkins instance"""
        url = self.config.base_url.with_path(url_path)
        response = self.session.head(
            str(url), timeout=self.timeout, allow_redirects=True
        )

        if response.status_code == 404:
            return False

        response.raise_for_status()

        return True

    def create_item(self, project_path: ProjectPath, xml: str) -> None:
        """Given the xml and project path create an item in Jenkins"""
        if self.project_exists(project_path):
            raise FileExistsError(project_path)

        parent_path = project_path.parent
        url = self.config.base_url.with_path(parent_path.url_path) / "createItem"
        params = {"name": project_path.name}
        headers = {"Content-Type": "text/xml"}

        response = self.session.post(
            str(url),
            data=xml,
            headers=headers,
            params=params,
            timeout=self.config.requests_timeout,
        )

        if response.status_code == 404:
            raise FileNotFoundError(project_path.parent)

        response.raise_for_status()

    def get_item(self, project_path: ProjectPath) -> str:
        """Return the xml definition for the given project"""
        url = self.config.base_url.with_path(project_path.url_path) / "config.xml"

        response = self.session.get(str(url), timeout=self.config.requests_timeout)

        if response.status_code == 404:
            raise FileNotFoundError(project_path.parent)

        response.raise_for_status()

        return response.text

    def make_folder(
        self, project_path: ProjectPath, parents: bool = False, exist_ok: bool = False
    ) -> None:
        """Create a project folder with the given path"""
        if project_path == ProjectPath():
            # Cannot create the root
            if not exist_ok:
                raise FileExistsError(project_path)

            return

        if parents:
            parent = project_path.parent

            if parent != ProjectPath():
                self.make_folder(parent, parents=True, exist_ok=True)

        try:
            self.create_item(project_path, FOLDER_XML)
        except FileExistsError:
            if not exist_ok or not self.is_folder(project_path):
                raise

    def is_folder(self, project_path: ProjectPath) -> bool:
        """Return True if project_path is a folder"""
        try:
            xml = self.get_item(project_path)
        except FileNotFoundError:
            return False

        tree = ET.fromstring(xml)

        return tree.tag == "com.cloudbees.hudson.plugins.folder.Folder"

    def install_plugin(self, plugin: str) -> None:
        """Ensure the given plugin is installed.

        Jenkins uses name@version syntax for `plugin`, for example "copyartifact@1.47"
        """
        url = self.config.base_url.with_path("/pluginManager/installNecessaryPlugins")
        response = self.session.post(
            str(url),
            headers={"Content-Type": "text/xml"},
            data=f'<jenkins><install plugin="{plugin}" /></jenkins>',
        )

        response.raise_for_status()

    def create_repo_job(self, repo_name: str, repo_url: str, repo_branch: str) -> None:
        """Create a repo job in the "repos" folder

        Assumes that the "repos" folder exists under the project root.
        """
        repo_path = self.project_root / "repos" / repo_name

        self.create_item(repo_path, self.render_build_repo_xml(repo_url, repo_branch))

    def render_build_repo_xml(self, repo_url: str, repo_branch: str) -> str:
        """Return XML config for the given repo"""
        xml = ET.fromstring(CREATE_REPO_XML)

        branch = xml.find("scm/branches/hudson.plugins.git.BranchSpec/name")
        assert branch is not None
        branch.text = f"*/{repo_branch}"

        url = xml.find("scm/userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url")
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

        repos_path = (
            "properties"
            "/org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty"
            "/triggers"
            "/jenkins.triggers.ReverseBuildTrigger/upstreamProjects"
        )
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
