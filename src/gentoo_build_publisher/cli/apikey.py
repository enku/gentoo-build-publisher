"""gbpcli apikey subcommand"""

import argparse
import secrets

import django.db.utils
from gbpcli import GBP, Console

import gentoo_build_publisher._django_setup  # pylint: disable=unused-import
from gentoo_build_publisher.models import ApiKey
from gentoo_build_publisher.settings import Settings


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """gbp apikey subcommand handler"""
    match args.action:
        case "create":
            return create_action(args, console)
    return 0


def parse_args(parser: argparse.ArgumentParser) -> None:
    """Set up parser arguments"""
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparser = subparsers.add_parser(
        "create", description="Create an API key with the given name"
    )
    subparser.add_argument("name", type=str, help="Unique name for the key")


def create_action(args: argparse.Namespace, console: Console) -> int:
    """handle the "create" action"""
    key = create_api_key()

    try:
        obj = save_api_key(key, args.name)
    except django.db.utils.IntegrityError:
        console.err.print("An API key with that name already exists.")
        return 1

    console.out.print(obj.apikey)
    return 0


def create_api_key() -> str:
    """Create an API key"""
    settings = Settings.from_environ()

    return secrets.token_urlsafe(settings.API_KEY_LENGTH)


def save_api_key(api_key: str, name: str) -> ApiKey:
    """Save the given api_key to the repository with the given name"""
    return ApiKey.objects.create(name=name.lower(), apikey=api_key)
