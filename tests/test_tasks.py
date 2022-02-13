"""Unit tests for the tasks module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=no-value-for-parameter,no-self-use
import os
from unittest import mock

from requests import HTTPError

from gentoo_build_publisher.build import BuildID
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.tasks import (
    delete_build,
    publish_build,
    pull_build,
    purge_build,
)

from . import MockJenkins, TestCase


class PublishBuildTestCase(TestCase):
    """Unit tests for tasks.publish_build"""

    @mock.patch("gentoo_build_publisher.managers.Jenkins", new=MockJenkins)
    def test_publishes_build(self):
        """Should actually publish the build"""
        with mock.patch("gentoo_build_publisher.tasks.purge_build"):
            result = publish_build.s("babette", 193).apply()

        buildman = BuildMan(BuildID("babette.193"))
        self.assertIs(buildman.published(), True)
        self.assertIs(result.result, True)

    @mock.patch("gentoo_build_publisher.tasks.logger.error")
    def test_should_give_up_when_publish_raises_httperror(self, log_error_mock):
        with mock.patch("gentoo_build_publisher.tasks.pull_build.apply") as apply_mock:
            apply_mock.side_effect = HTTPError
            result = publish_build.s("babette", 193).apply()

        self.assertIs(result.result, False)

        log_error_mock.assert_called_with(
            "Build %s failed to pull. Not publishing", "babette.193"
        )


class PurgeBuildTestCase(TestCase):
    """Tests for the purge_build task"""

    @mock.patch("gentoo_build_publisher.tasks.BuildMan.purge")
    def test(self, purge_mock):
        purge_build.s("foo").apply()

        purge_mock.assert_called_once_with("foo")


class PullBuildTestCase(TestCase):
    """Tests for the pull_build task"""

    @mock.patch("gentoo_build_publisher.managers.Jenkins", new=MockJenkins)
    def test_pulls_build(self):
        """Should actually pull the build"""
        with mock.patch("gentoo_build_publisher.tasks.purge_build"):
            pull_build.s("lima", 1012).apply()

        buildman = BuildMan(BuildID("lima.1012"))
        self.assertIs(buildman.pulled(), True)

    @mock.patch("gentoo_build_publisher.managers.Jenkins", new=MockJenkins)
    def test_calls_purge_build(self):
        """Should issue the purge_build task when setting is true"""
        with mock.patch("gentoo_build_publisher.tasks.purge_build") as mock_purge_build:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "1"}):
                pull_build.s("charlie", 197).apply()

        mock_purge_build.delay.assert_called_with("charlie")

    @mock.patch("gentoo_build_publisher.managers.Jenkins", new=MockJenkins)
    def test_does_not_call_purge_build(self):
        """Should not issue the purge_build task when setting is false"""
        with mock.patch("gentoo_build_publisher.tasks.purge_build") as mock_purge_build:
            with mock.patch.dict(os.environ, {"BUILD_PUBLISHER_ENABLE_PURGE": "0"}):
                pull_build.s("delta", 424).apply()

        mock_purge_build.delay.assert_not_called()

    @mock.patch("gentoo_build_publisher.tasks.logger.error", new=mock.Mock())
    def test_should_delete_db_model_when_download_fails(self):
        with mock.patch(
            "gentoo_build_publisher.managers.Jenkins.download_artifact"
        ) as download_artifact_mock:
            download_artifact_mock.side_effect = HTTPError
            pull_build.s("oscar", 197).apply()

        with self.assertRaises(BuildDB.NotFound):
            BuildDB.get(BuildID("oscar.197"))

    @mock.patch("gentoo_build_publisher.tasks.logger.error", new=mock.Mock())
    def test_should_not_retry_on_404_response(self):
        with mock.patch(
            "gentoo_build_publisher.managers.Jenkins.download_artifact"
        ) as download_artifact_mock:
            error = HTTPError()
            error.response = mock.Mock()
            error.response.status_code = 404
            download_artifact_mock.side_effect = error

            with mock.patch.object(pull_build, "retry") as retry_mock:
                pull_build.s("tango", 197).apply()

        retry_mock.assert_not_called()


class DeleteBuildTestCase(TestCase):
    """Unit tests for tasks_delete_build"""

    def test_should_delete_the_build(self):
        with mock.patch("gentoo_build_publisher.tasks.BuildMan") as buildman_mock:
            delete_build.s("zulu", 56).apply()

        buildman_mock.assert_called_once_with("zulu.56")
        task_buildman = buildman_mock.return_value
        task_buildman.delete.assert_called_once_with()
