"""Tests for gentoo build publisher"""
# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name
import datetime as dt
import io
import json
import logging
import math
import os
import tarfile
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Union
from unittest import TestCase as UnitTestTestCase
from unittest import mock

import django.test

from gentoo_build_publisher import publisher
from gentoo_build_publisher.jenkins import Jenkins, JenkinsConfig, JenkinsMetadata
from gentoo_build_publisher.types import Build, Content, Package

BASE_DIR = Path(__file__).resolve().parent / "data"


logging.basicConfig(handlers=[logging.NullHandler()])


class TestCase(django.test.TestCase):
    def setUp(self):
        # pylint: disable=import-outside-toplevel,cyclic-import
        from .factories import BuildPublisherFactory

        super().setUp()

        tmpdir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(tmpdir.cleanup)
        self.tmpdir = Path(tmpdir.name)
        patch = mock.patch.dict(
            os.environ,
            {
                "BUILD_PUBLISHER_STORAGE_PATH": tmpdir.name,
                "BUILD_PUBLISHER_JENKINS_BASE_URL": "https://jenkins.invalid/",
                "BUILD_PUBLISHER_RECORDS_BACKEND": "django",
            },
        )
        self.addCleanup(patch.stop)
        patch.start()

        self.publisher = BuildPublisherFactory()
        patch = mock.patch.object(publisher, "_PUBLISHER", new=self.publisher)
        self.addCleanup(patch.stop)
        patch.start()

        self.artifact_builder = self.publisher.jenkins.artifact_builder

    def create_file(self, name, content=b"", mtime=None):
        path = self.tmpdir / name

        with path.open("wb") as outfile:
            outfile.write(content)

        if mtime is not None:
            stat = os.stat(path)
            atime = stat.st_atime
            os.utime(path, times=(atime, mtime.timestamp()))

        return path


def parametrized(lists_of_args: Iterable[Iterable[Any]]) -> Callable:
    def dec(func: Callable):
        @wraps(func)
        def wrapper(self: UnitTestTestCase, *args: Any, **kwargs: Any) -> None:
            for list_of_args in lists_of_args:
                name = ",".join(str(i) for i in list_of_args)
                with self.subTest(name):
                    func(self, *args, *list_of_args, **kwargs)

        return wrapper

    return dec


def test_data(filename):
    """Return all the data in filename"""
    with open(BASE_DIR / filename, "rb") as file_obj:
        return file_obj.read()


class MockJenkins(Jenkins):
    """Jenkins with requests mocked out"""

    mock_get = None
    get_build_logs_mock_get = None

    def __init__(self, config: JenkinsConfig):
        # pylint: disable=import-outside-toplevel,cyclic-import
        from .factories import ArtifactFactory

        super().__init__(config)

        self.artifact_builder = ArtifactFactory()
        self.scheduled_builds: list[str] = []

    def download_artifact(self, build: Build):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.iter_content.side_effect = (
                lambda *args, **kwargs: self.artifact_builder.get_artifact(build)
            )
            self.mock_get = mock_get
            return super().download_artifact(build)

    def get_logs(self, build: Build):
        with mock.patch("gentoo_build_publisher.jenkins.requests.get") as mock_get:
            mock_get.return_value.text = "foo\n"
            self.get_build_logs_mock_get = mock_get

            return super().get_logs(build)

    def get_metadata(self, build: Build) -> JenkinsMetadata:
        build_time = self.artifact_builder.build_info(build).build_time
        return JenkinsMetadata(duration=124, timestamp=build_time)

    def schedule_build(self, machine: str) -> str:
        self.scheduled_builds.append(machine)

        return str(self.config.base_url / "job" / machine / "build")
