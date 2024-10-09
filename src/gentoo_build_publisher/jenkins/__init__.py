"""Jenkins api for Gentoo Build Publisher"""

from __future__ import annotations

import json as jsonlib
import logging
from dataclasses import dataclass
from functools import partial
from pathlib import PurePosixPath
from typing import Any, Iterable, Self

import requests
from yarl import URL

from gentoo_build_publisher.jenkins import xml
from gentoo_build_publisher.settings import JENKINS_DEFAULT_CHUNK_SIZE, Settings
from gentoo_build_publisher.types import Build, EbuildRepo, MachineJob
from gentoo_build_publisher.utils import dict_to_list_of_dicts, request_and_raise

AuthTuple = tuple[str, str]
logger = logging.getLogger(__name__)

COPY_ARTIFACT_PLUGIN = "copyartifact@1.47"
HTTP_NOT_FOUND = 404
PATH_SEPARATOR = "/"


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
    def from_settings(cls: type[Self], settings: Settings) -> Self:
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
        session = requests.Session()
        session.auth = config.auth()
        setattr(  # setattr confuses mypy so as not to give warning
            session,
            "request",
            partial(session.request, timeout=config.requests_timeout),
        )
        self.session = session
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
        http_response = request_and_raise(self.session.get, url, stream=True)

        return http_response.iter_content(
            chunk_size=self.config.download_chunk_size, decode_unicode=False
        )

    def get_logs(self, build: Build) -> str:
        """Get and return the build's jenkins logs"""
        url = self.url.logs(build)
        http_response = request_and_raise(self.session.get, url)

        return http_response.text

    def get_metadata(self, build: Build) -> JenkinsMetadata:
        """Query Jenkins for build's metadata"""
        url = self.url.metadata(build)
        http_response = request_and_raise(self.session.get, url)

        json = http_response.json()

        return JenkinsMetadata(duration=json["duration"], timestamp=json["timestamp"])

    @classmethod
    def from_settings(cls: type[Jenkins], settings: Settings) -> Jenkins:
        """Return a JenkinsBuild instance given settings"""
        config = JenkinsConfig.from_settings(settings)
        return cls(config)

    def schedule_build(self, machine: str, **build_params: Any) -> str | None:
        """Schedule a build on Jenkins

        `params` are build parameters to pass to the job instead of the defaults.
        """
        url = self.url.build_scheduler(machine)
        job_params = self.get_job_parameters(machine)
        params_list = build_params_list(job_params, build_params)
        json_params = jsonlib.dumps({"parameter": params_list})

        http_response = request_and_raise(
            self.session.post, url, data={"json": json_params}
        )

        # All that Jenkins (sometimes) gives us is the location of the queued request.
        # Let's return that.
        return http_response.headers.get("location")

    def project_exists(self, project_path: ProjectPath) -> bool:
        """Return True iff project_path exists on the Jenkins instance"""
        return self.url_path_exists(project_path.url_path)

    def url_path_exists(self, url_path: str) -> bool:
        """Return True iff url_path exists on the Jenkins instance"""
        url = self.config.base_url.with_path(url_path)
        http_response = request_and_raise(
            self.session.head, url, exclude=[HTTP_NOT_FOUND], allow_redirects=True
        )

        if http_response.status_code == HTTP_NOT_FOUND:
            return False

        return True

    def create_item(self, project_path: ProjectPath, xml_str: str) -> None:
        """Given the xml and project path create an item in Jenkins"""
        if self.project_exists(project_path):
            raise FileExistsError(project_path)

        parent_path = project_path.parent
        url = self.config.base_url.with_path(parent_path.url_path) / "createItem"
        params = {"name": project_path.name}
        headers = {"Content-Type": "text/xml"}

        http_response = request_and_raise(
            self.session.post,
            url,
            exclude=[HTTP_NOT_FOUND],
            data=xml_str,
            headers=headers,
            params=params,
        )

        if http_response.status_code == HTTP_NOT_FOUND:
            raise FileNotFoundError(project_path.parent)

    def get_item(self, project_path: ProjectPath) -> str:
        """Return the xml definition for the given project"""
        url = self.config.base_url.with_path(project_path.url_path) / "config.xml"

        http_response = request_and_raise(
            self.session.get, url, exclude=[HTTP_NOT_FOUND]
        )

        if http_response.status_code == HTTP_NOT_FOUND:
            raise FileNotFoundError(project_path.parent)

        return http_response.text

    def get_job_parameters(self, machine: str) -> dict[str, Any]:
        """Return the parameters for the machine's job

        Each parameter is a dict of name -> default_value
        """
        url = self.url.job(machine)
        params = {
            "tree": "property[parameterDefinitions[name,defaultParameterValue[value]]]"
        }

        http_response = request_and_raise(self.session.get, url, params=params)

        properties = http_response.json()["property"]
        props = [prop for prop in properties if "parameterDefinitions" in prop]

        if not props:
            return {}

        if len(props) != 1:  # pragma: no cover
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
            self.create_item(project_path, xml.FOLDER)
        except FileExistsError:
            self.maybe_raise_folderexists(project_path, exist_ok)

    def is_folder(self, project_path: ProjectPath) -> bool:
        """Return True if project_path is a folder"""
        if project_path == ProjectPath():
            return True
        try:
            xml_str = self.get_item(project_path)
        except FileNotFoundError:
            return False

        return xml.is_folder(xml_str)

    def maybe_raise_folderexists(self, folder: ProjectPath, exist_ok: bool) -> None:
        """Maybe raise FileExistsError"""
        if not exist_ok or not self.is_folder(folder):
            raise FileExistsError(folder)

    def install_plugin(self, plugin: str) -> None:
        """Ensure the given plugin is installed.

        Jenkins uses name@version syntax for `plugin`, for example "copyartifact@1.47"
        """
        url = self.config.base_url.with_path("/pluginManager/installNecessaryPlugins")
        request_and_raise(
            self.session.post,
            url,
            headers={"Content-Type": "text/xml"},
            data=xml.install_plugin(plugin),
        )

    def create_repo_job(self, repo: EbuildRepo) -> None:
        """Create a repo job in the "repos" folder

        Assumes that the "repos" folder exists under the project root.
        """
        repo_path = self.project_root / "repos" / repo.name

        self.create_item(repo_path, xml.build_repo(repo))

    def create_machine_job(self, job: MachineJob) -> None:
        """Create a machine job to build the given machine"""
        machine_path = self.project_root / job.name

        self.install_plugin(COPY_ARTIFACT_PLUGIN)
        self.create_item(machine_path, xml.build_machine(job))


def build_params_list(
    job_params: dict[str, Any], build_params: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return Jenkins-format parameter list based on the build_parameters

    job_params are a dict of parameters for the job.
    """
    # parameter logic here is based on
    # https://stackoverflow.com/questions/20359810/how-to-trigger-jenkins-builds-remotely-and-to-pass-parameters
    if keys := build_params.keys() - job_params.keys():
        raise ValueError(f"parameter(s) {sorted(keys)} are invalid for this build")

    return dict_to_list_of_dicts(job_params | build_params)
