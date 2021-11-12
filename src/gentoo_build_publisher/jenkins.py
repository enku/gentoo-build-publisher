"""Jenkins api for Gentoo Build Publisher"""
import logging
from dataclasses import dataclass
from typing import Iterator, Optional, Type, TypeVar

import requests
from dataclasses_json import dataclass_json
from yarl import URL

from gentoo_build_publisher import JENKINS_DEFAULT_CHUNK_SIZE
from gentoo_build_publisher.build import Build
from gentoo_build_publisher.settings import Settings

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


@dataclass
class JenkinsBuild:
    """A Build's interface to JenkinsBuild"""

    build: Build
    jenkins: JenkinsConfig

    def url(self) -> URL:
        """Return the Jenkins url for the build"""
        return self.jenkins.base_url / "job" / self.build.name / str(self.build.number)

    def artifact_url(self) -> URL:
        """Return the artifact url for build"""
        return self.url() / "artifact" / self.jenkins.artifact_name

    def logs_url(self) -> URL:
        """Return the url for the build's console logs"""
        return self.url() / "consoleText"

    def download_artifact(self) -> Iterator[bytes]:
        """Download and yield the build artifact in chunks of bytes"""
        url = self.artifact_url()
        response = requests.get(str(url), auth=self.jenkins.auth(), stream=True)
        response.raise_for_status()

        return response.iter_content(
            chunk_size=self.jenkins.download_chunk_size, decode_unicode=False
        )

    def get_logs(self) -> str:
        """Get and return the build's jenkins logs"""
        url = self.logs_url()
        response = requests.get(str(url), auth=self.jenkins.auth())
        response.raise_for_status()

        return response.text

    def get_metadata(self) -> JenkinsMetadata:
        """Query Jenkins for build's metadata"""
        url = self.url() / "api" / "json"
        response = requests.get(str(url), auth=self.jenkins.auth())
        response.raise_for_status()

        return JenkinsMetadata.from_dict(  # type: ignore  # pylint: disable=no-member
            response.json()
        )

    @classmethod
    def from_settings(cls, build: Build, settings: Settings):
        """Return a JenkinsBuild instance given settings"""
        jenkins = JenkinsConfig.from_settings(settings)
        return cls(build=build, jenkins=jenkins)


def schedule_build(name: str, settings: Settings) -> str:
    """Schedule a build on Jenkins"""
    jenkins_config = JenkinsConfig.from_settings(settings)
    url = jenkins_config.base_url / "job" / name / "build"
    response = requests.post(str(url), auth=jenkins_config.auth())
    response.raise_for_status()

    # All that Jenkins gives us is the location of the queued request.  Let's return
    # that.
    return response.headers["location"]
