"""Unit tests for the tasks module"""
# pylint: disable=missing-docstring,no-value-for-parameter
import os
from unittest import mock

from requests import HTTPError

from gentoo_build_publisher.common import Build
from gentoo_build_publisher.records import RecordNotFound, Records
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.tasks import (
    delete_build,
    publish_build,
    pull_build,
    purge_machine,
)

from . import TestCase


class PublishBuildTestCase(TestCase):
    """Unit tests for tasks.publish_build"""

    def test_publishes_build(self) -> None:
        """Should actually publish the build"""
        with mock.patch("gentoo_build_publisher.tasks.purge_machine"):
            result = publish_build.s("babette.193").apply()

        build = Build("babette", "193")
        self.assertIs(self.publisher.published(build), True)
        self.assertIs(result.result, True)

    @mock.patch("gentoo_build_publisher.tasks.logger.error")
    def test_should_give_up_when_publish_raises_httperror(self, log_error_mock) -> None:
        with mock.patch("gentoo_build_publisher.tasks.pull_build.apply") as apply_mock:
            apply_mock.side_effect = HTTPError
            result = publish_build.s("babette.193").apply()

        self.assertIs(result.result, False)

        log_error_mock.assert_called_with(
            "Build %s failed to pull. Not publishing", "babette.193"
        )


class PurgeBuildTestCase(TestCase):
    """Tests for the purge_machine task"""

    def test(self) -> None:
        with mock.patch.object(self.publisher, "purge") as purge_mock:
            purge_machine.s("foo").apply()

        purge_mock.assert_called_once_with("foo")


class PullBuildTestCase(TestCase):
    """Tests for the pull_build task"""

    def test_pulls_build(self) -> None:
        """Should actually pull the build"""
        with mock.patch("gentoo_build_publisher.tasks.purge_machine"):
            pull_build.s("lima.1012").apply()

        build = Build("lima", "1012")
        self.assertIs(self.publisher.pulled(build), True)

    def test_calls_purge_machine(self) -> None:
        """Should issue the purge_machine task when setting is true"""
        with mock.patch(
            "gentoo_build_publisher.tasks.purge_machine"
        ) as mock_purge_machine:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "1"}):
                pull_build.s("charlie.197").apply()

        mock_purge_machine.delay.assert_called_with("charlie")

    def test_does_not_call_purge_machine(self) -> None:
        """Should not issue the purge_machine task when setting is false"""
        with mock.patch(
            "gentoo_build_publisher.tasks.purge_machine"
        ) as mock_purge_machine:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "0"}):
                pull_build.s("delta.424").apply()

        mock_purge_machine.delay.assert_not_called()

    @mock.patch("gentoo_build_publisher.tasks.logger.error", new=mock.Mock())
    def test_should_delete_db_model_when_download_fails(self) -> None:
        settings = Settings.from_environ()
        records = Records.from_settings(settings)

        with mock.patch(
            "gentoo_build_publisher.publisher.Jenkins.download_artifact"
        ) as download_artifact_mock:
            download_artifact_mock.side_effect = Exception
            pull_build.s("oscar.197").apply()

        with self.assertRaises(RecordNotFound):
            records.get(Build("oscar", "197"))

    @mock.patch("gentoo_build_publisher.tasks.logger.error", new=mock.Mock())
    def test_should_retry_on_retryable_exceptions(self) -> None:
        with mock.patch(
            "gentoo_build_publisher.publisher.Jenkins.download_artifact"
        ) as download_artifact_mock:
            eof_error = EOFError()
            download_artifact_mock.side_effect = eof_error

            with mock.patch.object(pull_build, "retry") as retry_mock:
                pull_build.s("tango.197").apply()

        retry_mock.assert_called_once_with(exc=eof_error)

    @mock.patch("gentoo_build_publisher.tasks.logger.error", new=mock.Mock())
    def test_should_not_retry_on_404_response(self) -> None:
        with mock.patch(
            "gentoo_build_publisher.publisher.Jenkins.download_artifact"
        ) as download_artifact_mock:
            error = HTTPError()
            error.response = mock.Mock()
            error.response.status_code = 404
            download_artifact_mock.side_effect = error

            with mock.patch.object(pull_build, "retry") as retry_mock:
                pull_build.s("tango.197").apply()

        retry_mock.assert_not_called()


class DeleteBuildTestCase(TestCase):
    """Unit tests for tasks_delete_build"""

    def test_should_delete_the_build(self) -> None:
        with mock.patch.object(self.publisher, "delete") as mock_delete:
            delete_build.s("zulu.56").apply()

        mock_delete.assert_called_once_with(Build("zulu", "56"))
