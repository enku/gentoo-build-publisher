"""Jenkins api for Gentoo Build Publisher"""
import logging
from dataclasses import dataclass
from typing import Iterator, Optional

import requests
from yarl import URL

from gentoo_build_publisher import JENKINS_DEFAULT_CHUNK_SIZE
from gentoo_build_publisher.build import Build
from gentoo_build_publisher.settings import Settings

AuthTuple = tuple[str, str]
logger = logging.getLogger(__name__)


@dataclass
class JenkinsConfig:
    """Configuration for JenkinsBuild"""

    base_url: URL
    user: Optional[str] = None
    api_key: Optional[str] = None
    artifact_name: str = "build.tar.gz"
    download_chunk_size: int = JENKINS_DEFAULT_CHUNK_SIZE


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
        logger.info("Downloading build: %s", self.build)
        url = self.artifact_url()
        response = requests.get(str(url), auth=self.auth, stream=True)
        response.raise_for_status()

        return response.iter_content(
            chunk_size=self.jenkins.download_chunk_size, decode_unicode=False
        )

    def get_logs(self) -> str:
        """Get and return the build's jenkins logs"""
        url = self.logs_url()
        response = requests.get(str(url), auth=self.auth)
        response.raise_for_status()

        return response.text

    @classmethod
    def from_settings(cls, build: Build, settings: Settings):
        """Return a JenkinsBuild instance given settings"""
        jenkins = JenkinsConfig(
            base_url=URL(settings.JENKINS_BASE_URL),
            user=settings.JENKINS_USER,
            artifact_name=settings.JENKINS_ARTIFACT_NAME,
            api_key=settings.JENKINS_API_KEY,
            download_chunk_size=settings.JENKINS_DOWNLOAD_CHUNK_SIZE,
        )
        return cls(build=build, jenkins=jenkins)

    @property
    def auth(self) -> Optional[AuthTuple]:
        """The auth used for requests

        Either a 2-tuple or `None`
        """
        if self.jenkins.user is None or self.jenkins.api_key is None:
            return None

        return (self.jenkins.user, self.jenkins.api_key)
