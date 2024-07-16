# pylint: disable=missing-docstring,attribute-defined-outside-init
from argparse import ArgumentParser, Namespace
from unittest import mock

from gentoo_build_publisher.cli import worker

from . import TestCase


class WorkerTests(TestCase):
    """Tests for the worker gbpcli subcommand"""

    requires = ["publisher", "gbp", "console"]

    def test(self) -> None:
        worker_path = "gentoo_build_publisher.worker.rq.RQWorker.work"
        with mock.patch(worker_path) as mock_work:
            status = worker.handler(
                Namespace(type="rq"), self.fixtures.gbp, self.fixtures.console.console
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            self.fixtures.console.stdout.getvalue(),
            "Working for Gentoo Build Publisher!\n",
        )
        mock_work.assert_called_once()

    def test_parse_args(self) -> None:
        parser = ArgumentParser("gbp")
        worker.parse_args(parser)
