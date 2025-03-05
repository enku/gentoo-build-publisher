# pylint: disable=missing-docstring
from argparse import ArgumentParser, Namespace
from unittest import mock

from unittest_fixtures import Fixtures, given

from gbp_testkit import TestCase
from gentoo_build_publisher.cli import worker

# pylint: disable=unused-argument


@given("tmpdir", "publisher", "gbp", "console")
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

    def test_parse_args(self, fixtures: Fixtures) -> None:
        parser = ArgumentParser("gbp")
        worker.parse_args(parser)
