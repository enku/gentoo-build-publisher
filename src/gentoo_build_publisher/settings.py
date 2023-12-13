"""Settings for Gentoo Build Publisher"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, TypeVar

from gentoo_build_publisher.string import get_bool

JENKINS_DEFAULT_CHUNK_SIZE = 2 * 1024 * 1024


T = TypeVar("T", bound="BaseSettings")


@dataclass(frozen=True)
class BaseSettings:
    """Base class for Settings"""

    # Subclasses should define me as the prefix for environment variables for these
    # settings. For example if prefix is "BUILD_PUBLISHER_" and the field is named "FOO"
    # then the environment variable for that field is "BUILD_PUBLISHER_FOO"
    env_prefix: ClassVar = ""

    @classmethod
    def from_dict(cls: type[T], prefix: str, data_dict: dict[str, Any]) -> T:
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
    def from_environ(cls: type[T], prefix: str | None = None) -> T:
        """Return settings instantiated from environment variables"""
        if prefix is None:
            prefix = cls.env_prefix

        return cls.from_dict(prefix, dict(os.environ))


@dataclass(frozen=True, slots=True)
class Settings(BaseSettings):
    """GBP Settings"""

    # pylint: disable=invalid-name,too-many-instance-attributes
    env_prefix: ClassVar = "BUILD_PUBLISHER_"

    JENKINS_BASE_URL: str
    STORAGE_PATH: Path
    ENABLE_PURGE: bool = False
    JENKINS_API_KEY: str | None = None
    JENKINS_ARTIFACT_NAME: str = "build.tar.gz"
    JENKINS_DOWNLOAD_CHUNK_SIZE: int = JENKINS_DEFAULT_CHUNK_SIZE
    JENKINS_USER: str | None = None
    RECORDS_BACKEND: str = "django"
    WORKER_BACKEND: str = "celery"

    # Celery worker backend config
    WORKER_CELERY_CONCURRENCY: int = 1
    WORKER_CELERY_EVENTS: bool = False
    WORKER_CELERY_HOSTNAME: str = ""
    WORKER_CELERY_LOGLEVEL: str = "INFO"

    # RQ worker backend config
    WORKER_RQ_ASYNC: bool = True
    WORKER_RQ_NAME: str = ""
    WORKER_RQ_QUEUE_NAME: str = "gbp"
    WORKER_RQ_URL: str = "redis://localhost.invalid:6379"

    # ThreadWorker backend config
    WORKER_THREAD_WAIT: bool = False  # Wait on the running thread (True for testing)
