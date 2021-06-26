"""Jenkins api for Gentoo Build Publisher"""
from dataclasses import dataclass
from typing import Generator, Optional, Tuple

import requests
from yarl import URL

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.settings import Settings

AuthTuple = Tuple[str, str]


@dataclass
class JenkinsBuild:
    """A Build's interface to JenkinsBuild"""

    build: Build
    base_url: URL
    user: Optional[str] = None
    api_key: Optional[str] = None
    artifact_name: str = "build.tar.gz"

    def url(self) -> URL:
        """Return the Jenkins url for the build"""
        return self.base_url / "job" / self.build.name / str(self.build.number)

    def artifact_url(self) -> URL:
        """Return the artifact url for build"""
        return self.url() / "artifact" / self.artifact_name

    def logs_url(self) -> URL:
        """Return the url for the build's console logs"""
        return self.url() / "consoleText"

    def download_artifact(self) -> Generator[bytes, None, None]:
        """Download and yield the build artifact in chunks of bytes"""
        url = self.artifact_url()
        response = requests.get(str(url), auth=self.auth, stream=True)
        response.raise_for_status()

        return (
            bytes(i)
            for i in response.iter_content(chunk_size=2048, decode_unicode=False)
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
        return cls(
            build=build,
            base_url=URL(settings.JENKINS_BASE_URL),
            artifact_name=settings.JENKINS_ARTIFACT_NAME,
            user=settings.JENKINS_USER,
            api_key=settings.JENKINS_API_KEY,
        )

    @property
    def auth(self) -> Optional[AuthTuple]:
        """The auth used for requests

        Either a 2-tuple or `None`
        """
        if self.user is None or self.api_key is None:
            return None

        return (self.user, self.api_key)
