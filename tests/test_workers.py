"""Unit tests for the worker module"""

# pylint: disable=missing-docstring,no-value-for-parameter,unused-argument
import io
from contextlib import redirect_stderr
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, cast
from unittest import TestCase, mock

import fakeredis
from requests import HTTPError
from unittest_fixtures import Fixtures, given, parametrized, where

import gbp_testkit.fixtures as testkit
from gentoo_build_publisher import publisher
from gentoo_build_publisher.records import build_records
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import Build
from gentoo_build_publisher.worker import (
    Worker,
    WorkerInterface,
    WorkerNotFoundError,
    tasks,
)
from gentoo_build_publisher.worker.celery import CeleryWorker, celery_app
from gentoo_build_publisher.worker.rq import RQWorker
from gentoo_build_publisher.worker.sync import SyncWorker


def get_worker(name: str) -> WorkerInterface:
    settings = Settings(
        JENKINS_BASE_URL="http://jenkins.invalid/",
        WORKER_BACKEND=name,
        WORKER_RQ_ASYNC=False,
        WORKER_RQ_URL="redis://localhost.invalid:6379",
        STORAGE_PATH=Path("/dev/null"),
    )
    redis_path = "gentoo_build_publisher.worker.rq.Redis.from_url"
    mock_redis = fakeredis.FakeRedis()
    with mock.patch(redis_path, return_value=mock_redis):
        return Worker(settings)


def ifparams(*names: str) -> list[list[WorkerInterface]]:
    return [[get_worker(name)] for name in names]


def params(*names: str) -> Callable[..., Any]:
    return parametrized(ifparams(*names))


@given(testkit.publisher)
class PublishBuildTestCase(TestCase):
    """Unit tests for tasks.publish_build"""

    @params("celery", "rq", "sync", "thread")
    def test_publishes_build(self, worker: WorkerInterface, fixtures: Fixtures) -> None:
        """Should actually publish the build"""
        worker.run(tasks.publish_build, "babette.193")

        build = Build("babette", "193")
        self.assertIs(publisher.published(build), True)

    @params("celery", "rq", "sync", "thread")
    @mock.patch("gentoo_build_publisher.worker.logger.error")
    def test_should_give_up_when_pull_raises_httperror(
        self, worker: WorkerInterface, log_error_mock: mock.Mock, fixtures: Fixtures
    ) -> None:
        with mock.patch("gentoo_build_publisher.worker.tasks.pull_build") as apply_mock:
            apply_mock.side_effect = HTTPError
            worker.run(tasks.publish_build, "babette.193")

        log_error_mock.assert_called_with(
            "Build %s failed to pull. Not publishing", "babette.193"
        )


@given(testkit.publisher)
class PullBuildTestCase(TestCase):
    """Tests for the pull_build task"""

    @params("celery", "rq", "sync", "thread")
    def test_pulls_build(self, worker: WorkerInterface, fixtures: Fixtures) -> None:
        """Should actually pull the build"""
        worker.run(tasks.pull_build, "lima.1012", note=None, tags=None)

        build = Build("lima", "1012")
        self.assertIs(publisher.pulled(build), True)

    @params("celery", "rq", "sync", "thread")
    @mock.patch("gentoo_build_publisher.worker.logger.error", new=mock.Mock())
    def test_should_delete_db_model_when_download_fails(
        self, worker: WorkerInterface, fixtures: Fixtures
    ) -> None:
        settings = Settings.from_environ()
        records = build_records(settings)

        with mock.patch(
            "gentoo_build_publisher.build_publisher.Jenkins.download_artifact"
        ) as download_artifact_mock:
            download_artifact_mock.side_effect = RuntimeError("blah")
            with redirect_stderr(io.StringIO()):
                try:
                    worker.run(tasks.pull_build, "oscar.197", note=None, tags=None)
                except RuntimeError as error:
                    self.assertIs(error, download_artifact_mock.side_effect)

        self.assertFalse(records.exists(Build("oscar", "197")))


class DeleteBuildTestCase(TestCase):
    """Unit tests for tasks_delete_build"""

    @params("celery", "rq", "sync", "thread")
    def test_should_delete_the_build(self, worker: WorkerInterface) -> None:
        with mock.patch.object(publisher, "delete") as mock_delete:
            worker.run(tasks.delete_build, "zulu.56")

        mock_delete.assert_called_once_with(Build("zulu", "56"))


@given(testkit.environ, testkit.settings)
@where(
    environ={
        "BUILD_PUBLISHER_JENKINS_BASE_URL": "http://jenkins.invalid/",
        "BUILD_PUBLISHER_WORKER_BACKEND": "celery",
        "BUILD_PUBLISHER_WORKER_RQ_URL": "redis://localhost.invalid:6379",
        "BUILD_PUBLISHER_STORAGE_PATH": "/dev/null",
    }
)
class JobsTests(TestCase):
    def test_celery(self, fixtures: Fixtures) -> None:
        self.assertIsInstance(Worker(fixtures.settings), CeleryWorker)

    def test_rq(self, fixtures: Fixtures) -> None:
        settings = replace(fixtures.settings, WORKER_BACKEND="rq")
        worker = cast(RQWorker, Worker(settings))
        self.assertIsInstance(worker, RQWorker)
        self.assertEqual(
            worker.queue.connection.connection_pool.connection_kwargs,
            {"host": "localhost.invalid", "port": 6379},
        )

    def test_invalid(self, fixtures: Fixtures) -> None:
        settings = replace(fixtures.settings, WORKER_BACKEND="bogus")
        with self.assertRaises(WorkerNotFoundError):
            Worker(settings)


@given(testkit.settings)
@where(
    environ={
        "BUILD_PUBLISHER_JENKINS_BASE_URL": "http://jenkins.invalid/",
        "BUILD_PUBLISHER_WORKER_BACKEND": "rq",
        "BUILD_PUBLISHER_WORKER_CELERY_CONCURRENCY": "55",
        "BUILD_PUBLISHER_WORKER_CELERY_EVENTS": "True",
        "BUILD_PUBLISHER_WORKER_CELERY_HOSTNAME": "gbp.invalid",
        "BUILD_PUBLISHER_WORKER_CELERY_LOGLEVEL": "DEBUG",
        "BUILD_PUBLISHER_WORKER_RQ_NAME": "test-worker",
        "BUILD_PUBLISHER_WORKER_RQ_QUEUE_NAME": "test-queue",
        "BUILD_PUBLISHER_WORKER_RQ_URL": "redis://localhost.invalid:6379",
        "BUILD_PUBLISHER_STORAGE_PATH": "/dev/null",
    }
)
class WorkMethodTests(TestCase):
    """Tests for the WorkerInterface.work methods"""

    def test_celery(self, fixtures: Fixtures) -> None:
        path = "gentoo_build_publisher.worker.celery.Worker"
        with mock.patch(path) as mock_worker:
            CeleryWorker.work(fixtures.settings)

        mock_worker.assert_called_with(
            app=celery_app,
            concurrency=55,
            events=True,
            hostname="gbp.invalid",
            loglevel="DEBUG",
        )
        mock_worker.return_value.start.assert_called_once_with()

    def test_sync(self, fixtures: Fixtures) -> None:
        stderr_path = "gentoo_build_publisher.worker.sync.sys.stderr"
        with (
            self.assertRaises(SystemExit) as context,
            mock.patch(stderr_path) as mock_stderr,
        ):
            SyncWorker.work(fixtures.settings)

        self.assertEqual(context.exception.args, (1,))
        mock_stderr.write.assert_called_once_with("SyncWorker has no worker\n")

    def test_rq(self, fixtures: Fixtures) -> None:
        worker_path = "gentoo_build_publisher.worker.rq.Worker"
        redis_path = "gentoo_build_publisher.worker.rq.Redis"

        with (
            mock.patch(worker_path) as mock_worker,
            mock.patch(redis_path) as mock_redis,
        ):
            RQWorker.work(fixtures.settings)

        mock_redis.from_url.assert_called_once_with("redis://localhost.invalid:6379")
        connection = mock_redis.from_url.return_value
        mock_worker.assert_called_with(
            ["test-queue"], connection=connection, name="test-worker"
        )
        mock_worker.return_value.work.assert_called_once_with()
