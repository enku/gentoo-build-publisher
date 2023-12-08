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
    JENKINS_API_KEY: str | None = None
    JENKINS_ARTIFACT_NAME: str = "build.tar.gz"
    JENKINS_DOWNLOAD_CHUNK_SIZE: int = JENKINS_DEFAULT_CHUNK_SIZE
    JENKINS_USER: str | None = None
    JOBS_BACKEND: str = "celery"
    RECORDS_BACKEND: str = "django"

    # Celery jobs backend config
    CELERY_JOBS_CONCURRENCY: int = 1
    CELERY_JOBS_EVENTS: bool = False
    CELERY_JOBS_HOSTNAME: str = ""
    CELERY_JOBS_LOGLEVEL: str = "INFO"

    # RQ jobs backend config
    RQ_JOBS_ASYNC: bool = True
    RQ_JOBS_URL: str = "redis://localhost.invalid:6379"
    RQ_JOBS_NAME: str = ""

    @classmethod
    def from_dict(cls, prefix: str, data_dict: dict[str, Any]) -> Settings:
        """Return Settings instantiated from a dict"""
        params: dict[str, Any] = {}
        for field in fields(cls):
            if (key := f"{prefix}{field.name}") not in data_dict:
                continue

            match field.type:
                case "bool":
                    value = get_bool(data_dict[key])
                case "int":
                    value = int(data_dict[key])
                case "Path":
                    value = Path(data_dict[key])
                case _:
                    value = data_dict[key]

            params[field.name] = value
        return cls(**params)

    @classmethod
    def from_environ(cls, prefix: str = "BUILD_PUBLISHER_") -> Settings:
        """Return settings instantiated from environment variables"""
        return cls.from_dict(prefix, dict(os.environ))
