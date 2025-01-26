"""Task Worker for Gentoo Build Publisher

This is a simple wrapper that calls the appropriate worker according to
`settings.WORKER_BACKEND`.
"""

import argparse
from dataclasses import replace

from gbpcli.gbp import GBP
from gbpcli.types import Console

import gentoo_build_publisher._django_setup  # pylint: disable=unused-import
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.worker import Worker


def parse_args(parser: argparse.ArgumentParser) -> None:
    """Parse command-line arguments"""
    arg_help = """Type of worker backend to start.
(default: BUILD_PUBLISHER_WORKER_BACKEND environment variable)
"""
    parser.add_argument("--type", "-t", help=arg_help, default=None)


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """Run the Gentoo Build Publisher task worker"""
    settings = Settings.from_environ()

    if args.type:
        settings = replace(settings, WORKER_BACKEND=args.type)

    worker = Worker(settings)

    console.out.print("[bold][note]Working for Gentoo Build Publisher![/note][/bold]")
    worker.work(settings)

    return 0
