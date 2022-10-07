"""Jenkins api for Gentoo Build Publisher"""
from __future__ import annotations

import logging
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
        response = requests.get(
            str(url),
            auth=self.config.auth(),
            stream=True,
            timeout=self.config.requests_timeout,
        )
        response.raise_for_status()

        return response.iter_content(
            chunk_size=self.config.download_chunk_size, decode_unicode=False
        )

    def get_logs(self, build: Build) -> str:
        """Get and return the build's jenkins logs"""
        url = self.logs_url(build)
        response = requests.get(
            str(url), auth=self.config.auth(), timeout=self.config.requests_timeout
        )
        response.raise_for_status()

        return response.text

    def get_metadata(self, build: Build) -> JenkinsMetadata:
        """Query Jenkins for build's metadata"""
        url = self.url(build) / "api" / "json"
        response = requests.get(
            str(url), auth=self.config.auth(), timeout=self.config.requests_timeout
        )
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
        response = requests.post(
            str(url), auth=self.config.auth(), timeout=self.config.requests_timeout
        )
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
        response = requests.head(
            str(url),
            auth=self.config.auth(),
            timeout=self.config.requests_timeout,
            allow_redirects=True,
        )

        if response.status_code == 404:
            return False

        response.raise_for_status()

        return True
