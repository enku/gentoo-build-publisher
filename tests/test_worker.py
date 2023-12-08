# pylint: disable=missing-docstring
from argparse import ArgumentParser, Namespace
from unittest import mock

from gbpcli import GBP

from gentoo_build_publisher.cli import worker

from . import TestCase, string_console


class WorkerTests(TestCase):
    """Tests for the worker gbpcli subcommand"""

    def setUp(self) -> None:
        super().setUp()

        self.gbp = GBP("http://gbp.invalid/")
        self.console, self.stdout, self.stderr = string_console()

    def test(self) -> None:
        worker_path = "gentoo_build_publisher.jobs.rq.RQJobs.work"
        with mock.patch(worker_path) as mock_work:
            status = worker.handler(Namespace(type="rq"), self.gbp, self.console)

        self.assertEqual(status, 0)
        self.assertEqual(
            self.stdout.getvalue(), "Working for Gentoo Build Publisher!\n"
        )
        mock_work.assert_called_once()

    def test_parse_args(self) -> None:
        parser = ArgumentParser("gbp")
        worker.parse_args(parser)
