"""Settings for Gentoo Build Publisher"""
from __future__ import annotations

import os
from pathlib import PosixPath
from typing import Any, Optional

from pydantic import AnyHttpUrl, BaseModel  # pylint: disable=no-name-in-module


# NOTE: Using pydantic's BaseSettings was considered here but was considered too much
# "magic" and explicitly calling .from_environ() preferred.
class Settings(BaseModel):
    """GBP Settings"""

    ENABLE_PURGE: bool = False
    JENKINS_ARTIFACT_NAME: str = "build.tar.gz"
    JENKINS_API_KEY: Optional[str] = None
    JENKINS_BASE_URL: AnyHttpUrl
    JENKINS_DOWNLOAD_CHUNK_SIZE: int = 2 * 1024 * 1024
    JENKINS_USER: Optional[str] = None
    STORAGE_PATH: PosixPath

    @classmethod
    def from_dict(cls, prefix: str, data_dict: dict[str, Any]) -> Settings:
        """Return Settings instantiated from a dict"""
        return cls(
            **{
                key: value
                for key in cls.__fields__
                if (value := data_dict.get(f"{prefix}{key}")) is not None
            }
        )

    @classmethod
    def from_environ(cls, prefix: str = "BUILD_PUBLISHER_") -> Settings:
        """Return settings instantiated from environment variables"""
        return cls.from_dict(prefix, dict(os.environ))
