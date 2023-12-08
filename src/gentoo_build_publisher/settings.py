"""Settings for Gentoo Build Publisher"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from gentoo_build_publisher.string import get_bool

JENKINS_DEFAULT_CHUNK_SIZE = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Settings:
    """GBP Settings"""

    # pylint: disable=invalid-name,too-many-instance-attributes
    JENKINS_BASE_URL: str
    STORAGE_PATH: Path
    ENABLE_PURGE: bool = False
    JENKINS_ARTIFACT_NAME: str = "build.tar.gz"
    JENKINS_API_KEY: str | None = None
    JENKINS_DOWNLOAD_CHUNK_SIZE: int = JENKINS_DEFAULT_CHUNK_SIZE
    JENKINS_USER: str | None = None
    RECORDS_BACKEND: str = "django"
    JOBS_BACKEND: str = "celery"
    REDIS_JOBS_URL: str = "redis://localhost.invalid:6379"
    REDIS_JOBS_ASYNC: bool = True

    @classmethod
    def from_dict(cls, prefix: str, data_dict: dict[str, Any]) -> Settings:
        """Return Settings instantiated from a dict"""
        params: dict[str, Any] = {}
        field_names = [i.name for i in fields(cls)]

        for key, value in data_dict.items():
            if not key.startswith(prefix):
                continue

            match name := key.removeprefix(prefix):
                case "ENABLE_PURGE" | "REDIS_JOB_ASYNC":
                    params[name] = get_bool(value)
                case "JENKINS_DOWNLOAD_CHUNK_SIZE":
                    params[name] = int(value)
                case "STORAGE_PATH":
                    params[name] = Path(value)
                case _ if name in field_names:
                    params[name] = value

        return cls(**params)

    @classmethod
    def from_environ(cls, prefix: str = "BUILD_PUBLISHER_") -> Settings:
        """Return settings instantiated from environment variables"""
        return cls.from_dict(prefix, dict(os.environ))
