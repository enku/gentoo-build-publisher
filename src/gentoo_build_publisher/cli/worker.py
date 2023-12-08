"""Task Worker for Gentoo Build Publisher

This is a simple wrapper that calls the appropriate worker according to
`settings.JOBS_BACKEND`.
"""
import argparse
from dataclasses import replace

import django
from gbpcli import GBP, Console

from gentoo_build_publisher.jobs import get_interface_from_settings
from gentoo_build_publisher.settings import Settings


def parse_args(parser: argparse.ArgumentParser) -> None:
    """Parse command-line arguments"""
    arg_help = """Type of jobs backend to start.
(default: BUILD_PUBLISHER_JOBS_BACKEND environment variable)
"""
    parser.add_argument("--type", "-t", help=arg_help, default=None)


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """Run the Gentoo Build Publisher task worker"""
    django.setup()
    settings = Settings.from_environ()

    if args.type:
        settings = replace(settings, JOBS_BACKEND=args.type)

    iface = get_interface_from_settings(settings)

    console.out.print("[bold][note]Working for Gentoo Build Publisher![/note][/bold]")
    iface.work(settings)

    return 0
