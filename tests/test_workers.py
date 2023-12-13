"""Unit tests for the worker module"""
# pylint: disable=missing-docstring,no-value-for-parameter
import os
from pathlib import Path
from typing import Callable, cast
from unittest import mock

import fakeredis
from requests import HTTPError

from gentoo_build_publisher import celery as celery_app
from gentoo_build_publisher.common import Build
from gentoo_build_publisher.records import Records
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.worker import (
    Worker,
    WorkerInterface,
    WorkerNotFoundError,
    tasks,
)
from gentoo_build_publisher.worker.celery import CeleryWorker
from gentoo_build_publisher.worker.rq import RQWorker
from gentoo_build_publisher.worker.sync import SyncWorker

from . import TestCase, parametrized


def get_worker(name: str) -> WorkerInterface:
    Worker.cache_clear()
    settings = Settings(
        JENKINS_BASE_URL="http://jenkins.invalid/",
        WORKER_BACKEND=name,
        WORKER_RQ_ASYNC=False,
        WORKER_RQ_URL="redis://localhost.invalid:6379",
        STORAGE_PATH=Path("/dev/null"),
    )
    redis_path = "gentoo_build_publisher.worker.rq.Redis.from_url"
    mock_redis = fakeredis.FakeRedis()  # type: ignore[no-untyped-call]
    with mock.patch(redis_path, return_value=mock_redis):
        return Worker(settings)


def ifparams(*names: str) -> list[list[WorkerInterface]]:
    return [[get_worker(name)] for name in names]


def params(*names) -> Callable:
    return parametrized(ifparams(*names))


class PublishBuildTestCase(TestCase):
    """Unit tests for tasks.publish_build"""

    @params("celery", "rq", "sync", "thread")
    def test_publishes_build(self, worker: WorkerInterface) -> None:
        """Should actually publish the build"""
        worker.run(tasks.publish_build, "babette.193")

        build = Build("babette", "193")
        self.assertIs(self.publisher.published(build), True)

    @params("celery", "rq", "sync", "thread")
    @mock.patch("gentoo_build_publisher.worker.logger.error")
    def test_should_give_up_when_pull_raises_httperror(
        self, worker: WorkerInterface, log_error_mock: mock.Mock
    ) -> None:
        with mock.patch("gentoo_build_publisher.worker.tasks.pull_build") as apply_mock:
            apply_mock.side_effect = HTTPError
            worker.run(tasks.publish_build, "babette.193")

        log_error_mock.assert_called_with(
            "Build %s failed to pull. Not publishing", "babette.193"
        )


class PurgeBuildTestCase(TestCase):
    """Tests for the purge_machine task"""

    @params("celery", "rq", "sync", "thread")
    def test(self, worker: WorkerInterface) -> None:
        with mock.patch.object(
            self.publisher, "purge", wraps=self.publisher.purge
        ) as purge_mock:
            worker.run(tasks.purge_machine, "foo")

        purge_mock.assert_called_once_with("foo")


class PullBuildTestCase(TestCase):
    """Tests for the pull_build task"""

    @params("celery", "rq", "sync", "thread")
    def test_pulls_build(self, worker: WorkerInterface) -> None:
        """Should actually pull the build"""
        worker.run(tasks.pull_build, "lima.1012", note=None)

        build = Build("lima", "1012")
        self.assertIs(self.publisher.pulled(build), True)

    @params("celery", "rq", "sync", "thread")
    def test_calls_purge_machine(self, worker: WorkerInterface) -> None:
        """Should issue the purge_machine task when setting is true"""
        with mock.patch(
            "gentoo_build_publisher.worker.tasks.purge_machine"
        ) as mock_purge_machine:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "1"}):
                worker.run(tasks.pull_build, "charlie.197", note=None)

        mock_purge_machine.assert_called_with("charlie")

    @params("celery", "rq", "sync", "thread")
    def test_does_not_call_purge_machine(self, worker: WorkerInterface) -> None:
        """Should not issue the purge_machine task when setting is false"""
        with mock.patch(
            "gentoo_build_publisher.worker.tasks.purge_machine"
        ) as mock_purge_machine:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "0"}):
                worker.run(tasks.pull_build, "delta.424", note=None)

        mock_purge_machine.assert_not_called()

    @params("celery", "rq", "sync", "thread")
    @mock.patch("gentoo_build_publisher.worker.logger.error", new=mock.Mock())
    def test_should_delete_db_model_when_download_fails(
        self, worker: WorkerInterface
    ) -> None:
        settings = Settings.from_environ()
        records = Records.from_settings(settings)

        with mock.patch(
            "gentoo_build_publisher.publisher.Jenkins.download_artifact"
        ) as download_artifact_mock:
            download_artifact_mock.side_effect = RuntimeError("blah")
            try:
                worker.run(tasks.pull_build, "oscar.197", note=None)
            except RuntimeError as error:
                self.assertIs(error, download_artifact_mock.side_effect)

        self.assertFalse(records.exists(Build("oscar", "197")))


class DeleteBuildTestCase(TestCase):
    """Unit tests for tasks_delete_build"""

    @params("celery", "rq", "sync", "thread")
    def test_should_delete_the_build(self, worker: WorkerInterface) -> None:
        with mock.patch(
            "gentoo_build_publisher.publisher.BuildPublisher.delete"
        ) as mock_delete:
            worker.run(tasks.delete_build, "zulu.56")

        mock_delete.assert_called_once_with(Build("zulu", "56"))


class JobsTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Worker.cache_clear()

    def test_celery(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            WORKER_BACKEND="celery",
            WORKER_RQ_URL="redis://localhost.invalid:6379",
            STORAGE_PATH=Path("/dev/null"),
        )
        self.assertIsInstance(Worker(settings), CeleryWorker)

    def test_rq(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            WORKER_BACKEND="rq",
            WORKER_RQ_URL="redis://localhost.invalid:6379",
            STORAGE_PATH=Path("/dev/null"),
        )
        worker = cast(RQWorker, Worker(settings))
        self.assertIsInstance(worker, RQWorker)
        self.assertEqual(
            worker.queue.connection.connection_pool.connection_kwargs,
            {"host": "localhost.invalid", "port": 6379},
        )

    def test_invalid(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            WORKER_BACKEND="bogus",
            WORKER_RQ_URL="redis://localhost.invalid:6379",
            STORAGE_PATH=Path("/dev/null"),
        )
        with self.assertRaises(WorkerNotFoundError):
            Worker(settings)


class WorkMethodTests(TestCase):
    """Tests for the WorkerInterface.work methods"""

    def setUp(self) -> None:
        super().setUp()

        self.settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            WORKER_BACKEND="rq",
            WORKER_CELERY_CONCURRENCY=55,
            WORKER_CELERY_EVENTS=True,
            WORKER_CELERY_HOSTNAME="gbp.invalid",
            WORKER_CELERY_LOGLEVEL="DEBUG",
            WORKER_RQ_NAME="test-worker",
            WORKER_RQ_QUEUE_NAME="test-queue",
            WORKER_RQ_URL="redis://localhost.invalid:6379",
            STORAGE_PATH=Path("/dev/null"),
        )

    def test_celery(self) -> None:
        path = "gentoo_build_publisher.worker.celery.Worker"
        with mock.patch(path) as mock_worker:
            CeleryWorker.work(self.settings)

        mock_worker.assert_called_with(
            app=celery_app,
            concurrency=55,
            events=True,
            hostname="gbp.invalid",
            loglevel="DEBUG",
        )
        mock_worker.return_value.start.assert_called_once_with()

    def test_sync(self) -> None:
        stderr_path = "gentoo_build_publisher.worker.sync.sys.stderr"
        with self.assertRaises(SystemExit) as context, mock.patch(
            stderr_path
        ) as mock_stderr:
            SyncWorker.work(self.settings)

        self.assertEqual(context.exception.args, (1,))
        mock_stderr.write.assert_called_once_with("SyncWorker has no worker\n")

    def test_rq(self) -> None:
        worker_path = "gentoo_build_publisher.worker.rq.Worker"
        redis_path = "gentoo_build_publisher.worker.rq.Redis"

        with mock.patch(worker_path) as mock_worker, mock.patch(
            redis_path
        ) as mock_redis:
            RQWorker.work(self.settings)

        mock_redis.from_url.assert_called_once_with("redis://localhost.invalid:6379")
        connection = mock_redis.from_url.return_value
        mock_worker.assert_called_with(
            ["test-queue"], connection=connection, name="test-worker"
        )
        mock_worker.return_value.work.assert_called_once_with()
