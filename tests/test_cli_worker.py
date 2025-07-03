# pylint: disable=missing-docstring
from argparse import ArgumentParser, Namespace
from unittest import TestCase, mock

from unittest_fixtures import Fixtures, given, where

import gbp_testkit.fixtures as testkit
from gentoo_build_publisher.cli import worker
from gentoo_build_publisher.settings import Settings

# pylint: disable=unused-argument


@given(testkit.environ, testkit.tmpdir, testkit.publisher, testkit.gbp, testkit.console)
@where(environ={"BUILD_PUBLISHER_WORKER_BACKEND": "test"})
class WorkerTests(TestCase):
    """Tests for the worker gbpcli subcommand"""

    def test(self, fixtures: Fixtures) -> None:
        worker_path = "gentoo_build_publisher.worker.rq.RQWorker.work"
        with mock.patch(worker_path) as mock_work:
            status = worker.handler(
                Namespace(type="rq"), fixtures.gbp, fixtures.console
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            fixtures.console.out.file.getvalue(),
            "Working for Gentoo Build Publisher!\n",
        )
        mock_work.assert_called_once()

    def test_takes_type_from_settings_when_not_specified(
        self, fixtures: Fixtures
    ) -> None:
        args = Namespace(type=None)
        settings = Settings.from_environ()
        with mock.patch("gentoo_build_publisher.cli.worker.Worker") as mock_worker:
            status = worker.handler(args, fixtures.gbp, fixtures.console)

        self.assertEqual(status, 0)
        mock_worker.assert_called_once_with(settings)

    def test_parse_args(self, fixtures: Fixtures) -> None:
        parser = ArgumentParser("gbp")
        worker.parse_args(parser)
