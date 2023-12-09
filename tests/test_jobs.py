"""Unit tests for the jobs module"""
# pylint: disable=missing-docstring,no-value-for-parameter
import os
from pathlib import Path
from typing import Callable
from unittest import mock

import fakeredis
from requests import HTTPError

from gentoo_build_publisher import celery as celery_app
from gentoo_build_publisher import jobs
from gentoo_build_publisher.common import Build
from gentoo_build_publisher.jobs.celery import CeleryJobs
from gentoo_build_publisher.jobs.rq import RQJobs
from gentoo_build_publisher.jobs.sync import SyncJobs
from gentoo_build_publisher.records import Records
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.tasks import pull_build as celery_pull_build

from . import TestCase, parametrized


def set_job(name: str) -> jobs.JobsInterface:
    jobs.from_settings.cache_clear()
    settings = Settings(
        JENKINS_BASE_URL="http://jenkins.invalid/",
        JOBS_BACKEND=name,
        JOBS_RQ_ASYNC=False,
        JOBS_RQ_URL="redis://localhost.invalid:6379",
        STORAGE_PATH=Path("/dev/null"),
    )
    redis_path = "gentoo_build_publisher.jobs.rq.Redis.from_url"
    mock_redis = fakeredis.FakeRedis()  # type: ignore[no-untyped-call]
    with mock.patch(redis_path, return_value=mock_redis):
        return jobs.from_settings(settings)


def ifparams(*names: str) -> list[list[jobs.JobsInterface]]:
    return [[set_job(name)] for name in names]


def params(*names) -> Callable:
    return parametrized(ifparams(*names))


class PublishBuildTestCase(TestCase):
    """Unit tests for tasks.publish_build"""

    @params("celery", "rq", "sync")
    def test_publishes_build(self, jobif: jobs.JobsInterface) -> None:
        """Should actually publish the build"""
        jobif.publish_build("babette.193")

        build = Build("babette", "193")
        self.assertIs(self.publisher.published(build), True)

    @params("celery", "rq", "sync")
    @mock.patch("gentoo_build_publisher.jobs.logger.error")
    def test_should_give_up_when_pull_raises_httperror(
        self, jobif: jobs.JobsInterface, log_error_mock: mock.Mock
    ) -> None:
        with mock.patch("gentoo_build_publisher.jobs.pull_build") as apply_mock:
            apply_mock.side_effect = HTTPError
            jobif.publish_build("babette.193")

        log_error_mock.assert_called_with(
            "Build %s failed to pull. Not publishing", "babette.193"
        )


class PurgeBuildTestCase(TestCase):
    """Tests for the purge_machine task"""

    @params("celery", "rq", "sync")
    def test(self, jobif: jobs.JobsInterface) -> None:
        with mock.patch.object(
            self.publisher, "purge", wraps=self.publisher.purge
        ) as purge_mock:
            jobif.purge_machine("foo")

        purge_mock.assert_called_once_with("foo")


class PullBuildTestCase(TestCase):
    """Tests for the pull_build task"""

    @params("celery", "rq", "sync")
    def test_pulls_build(self, jobif: jobs.JobsInterface) -> None:
        """Should actually pull the build"""
        jobif.pull_build("lima.1012")

        build = Build("lima", "1012")
        self.assertIs(self.publisher.pulled(build), True)

    @params("celery", "rq", "sync")
    def test_calls_purge_machine(self, jobif: jobs.JobsInterface) -> None:
        """Should issue the purge_machine task when setting is true"""
        with mock.patch(
            "gentoo_build_publisher.jobs.purge_machine"
        ) as mock_purge_machine:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "1"}):
                jobif.pull_build("charlie.197")

        mock_purge_machine.assert_called_with("charlie")

    @params("celery", "rq", "sync")
    def test_does_not_call_purge_machine(self, jobif: jobs.JobsInterface) -> None:
        """Should not issue the purge_machine task when setting is false"""
        with mock.patch(
            "gentoo_build_publisher.tasks.purge_machine"
        ) as mock_purge_machine:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "0"}):
                jobif.pull_build("delta.424")

        mock_purge_machine.delay.assert_not_called()

    @params("celery", "rq", "sync")
    @mock.patch("gentoo_build_publisher.jobs.logger.error", new=mock.Mock())
    def test_should_delete_db_model_when_download_fails(
        self, jobif: jobs.JobsInterface
    ) -> None:
        settings = Settings.from_environ()
        records = Records.from_settings(settings)

        with mock.patch(
            "gentoo_build_publisher.publisher.Jenkins.download_artifact"
        ) as download_artifact_mock:
            download_artifact_mock.side_effect = RuntimeError("blah")
            try:
                jobif.pull_build("oscar.197")
            except RuntimeError as error:
                self.assertIs(error, download_artifact_mock.side_effect)

        self.assertFalse(records.exists(Build("oscar", "197")))

    @params("celery")
    @mock.patch("gentoo_build_publisher.jobs.logger.error", new=mock.Mock())
    def test_should_retry_on_retryable_exceptions(
        self, jobif: jobs.JobsInterface
    ) -> None:
        with mock.patch(
            "gentoo_build_publisher.publisher.Jenkins.download_artifact"
        ) as download_artifact_mock:
            eof_error = EOFError()
            download_artifact_mock.side_effect = eof_error

            with mock.patch.object(celery_pull_build, "retry") as retry_mock:
                jobif.pull_build("tango.197")

        retry_mock.assert_called_once_with(exc=eof_error)

    @params("celery")
    @mock.patch("gentoo_build_publisher.jobs.logger.error", new=mock.Mock())
    def test_should_not_retry_on_404_response(self, jobif: jobs.JobsInterface) -> None:
        with mock.patch(
            "gentoo_build_publisher.publisher.Jenkins.download_artifact"
        ) as download_artifact_mock:
            error = HTTPError()
            error.response = mock.Mock()
            error.response.status_code = 404
            download_artifact_mock.side_effect = error

            with mock.patch.object(celery_pull_build, "retry") as retry_mock:
                jobif.pull_build("tango.197")

        retry_mock.assert_not_called()


class DeleteBuildTestCase(TestCase):
    """Unit tests for tasks_delete_build"""

    @params("celery", "rq", "sync")
    def test_should_delete_the_build(self, jobif: jobs.JobsInterface) -> None:
        with mock.patch.object(self.publisher, "delete") as mock_delete:
            jobif.delete_build("zulu.56")

        mock_delete.assert_called_once_with(Build("zulu", "56"))


class JobsTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        jobs.from_settings.cache_clear()

    def test_celery(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            JOBS_BACKEND="celery",
            JOBS_RQ_URL="redis://localhost.invalid:6379",
            STORAGE_PATH=Path("/dev/null"),
        )
        self.assertIsInstance(jobs.from_settings(settings), CeleryJobs)

    def test_rq(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            JOBS_BACKEND="rq",
            JOBS_RQ_URL="redis://localhost.invalid:6379",
            STORAGE_PATH=Path("/dev/null"),
        )
        jobsif = jobs.from_settings(settings)
        self.assertIsInstance(jobsif, RQJobs)
        self.assertEqual(
            jobsif.queue.connection.connection_pool.connection_kwargs,
            {"host": "localhost.invalid", "port": 6379},
        )

    def test_invalid(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            JOBS_BACKEND="bogus",
            JOBS_RQ_URL="redis://localhost.invalid:6379",
            STORAGE_PATH=Path("/dev/null"),
        )
        with self.assertRaises(jobs.JobInterfaceNotFoundError):
            jobs.from_settings(settings)


class WorkMethodTests(TestCase):
    """Tests for the JobsInterface.work methods"""

    def setUp(self) -> None:
        super().setUp()

        self.settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            JOBS_BACKEND="rq",
            JOBS_CELERY_CONCURRENCY=55,
            JOBS_CELERY_EVENTS=True,
            JOBS_CELERY_HOSTNAME="gbp.invalid",
            JOBS_CELERY_LOGLEVEL="DEBUG",
            JOBS_RQ_NAME="test-worker",
            JOBS_RQ_QUEUE_NAME="test-queue",
            JOBS_RQ_URL="redis://localhost.invalid:6379",
            STORAGE_PATH=Path("/dev/null"),
        )

    def test_celery(self) -> None:
        path = "gentoo_build_publisher.jobs.celery.Worker"
        with mock.patch(path) as mock_worker:
            CeleryJobs.work(self.settings)

        mock_worker.assert_called_with(
            app=celery_app,
            concurrency=55,
            events=True,
            hostname="gbp.invalid",
            loglevel="DEBUG",
        )
        mock_worker.return_value.start.assert_called_once_with()

    def test_sync(self) -> None:
        stderr_path = "gentoo_build_publisher.jobs.sync.sys.stderr"
        with self.assertRaises(SystemExit) as context, mock.patch(
            stderr_path
        ) as mock_stderr:
            SyncJobs.work(self.settings)

        self.assertEqual(context.exception.args, (1,))
        mock_stderr.write.assert_called_once_with("SyncJobs has no worker\n")

    def test_rq(self) -> None:
        worker_path = "gentoo_build_publisher.jobs.rq.Worker"
        redis_path = "gentoo_build_publisher.jobs.rq.Redis"

        with mock.patch(worker_path) as mock_worker, mock.patch(
            redis_path
        ) as mock_redis:
            RQJobs.work(self.settings)

        mock_redis.from_url.assert_called_once_with("redis://localhost.invalid:6379")
        connection = mock_redis.from_url.return_value
        mock_worker.assert_called_with(
            ["test-queue"], connection=connection, name="test-worker"
        )
        mock_worker.return_value.work.assert_called_once_with()
