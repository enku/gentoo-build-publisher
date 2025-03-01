"""Settings for Gentoo Build Publisher"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from gbpcli.settings import BaseSettings

JENKINS_DEFAULT_CHUNK_SIZE = 2 * 1024 * 1024


@dataclass(kw_only=True, frozen=True, slots=True)
class Settings(BaseSettings):
    """GBP Settings"""

    # pylint: disable=invalid-name,too-many-instance-attributes
    env_prefix: ClassVar = "BUILD_PUBLISHER_"

    STORAGE_PATH: Path
    JENKINS_BASE_URL: str
    JENKINS_API_KEY: str | None = None
    JENKINS_ARTIFACT_NAME: str = "build.tar.gz"
    JENKINS_DOWNLOAD_CHUNK_SIZE: int = JENKINS_DEFAULT_CHUNK_SIZE
    JENKINS_USER: str | None = None
    RECORDS_BACKEND: str = "django"
    WORKER_BACKEND: str = "celery"
    API_KEY_ENABLE: bool = True
    API_KEY_LENGTH: int = 24

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
    WORKER_RQ_TASK_TIMEOUT: int = 1800  # seconds

    # ThreadWorker backend config
    WORKER_THREAD_WAIT: bool = False  # Wait on the running thread (True for testing)
