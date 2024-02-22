"""gbpcli apikey subcommand"""

import argparse
import secrets

from django.db import IntegrityError, transaction
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
        with transaction.atomic():
            obj = save_api_key(key, args.name)
    except IntegrityError:
        console.err.print("An API key with that name already exists.")
        return 1
    except KeyNameError as error:
        console.err.print(str(error.args[0]))
        return 2

    console.out.print(obj.apikey)
    return 0


def create_api_key() -> str:
    """Create an API key"""
    settings = Settings.from_environ()

    return secrets.token_urlsafe(settings.API_KEY_LENGTH)


def save_api_key(api_key: str, name: str) -> ApiKey:
    """Save the given api_key to the repository with the given name"""
    validate_key_name(name)

    return ApiKey.objects.create(name=name.lower(), apikey=api_key)


class KeyNameError(ValueError):
    """The name for the key is invalid"""


def validate_key_name(name: str) -> None:
    """Validate the key name

    Raise KeyNameError if the name is invalid
    """
    name_len = len(name)

    if name_len > 128:
        raise KeyNameError("Key name must not exceed 128 characters")

    if name_len == 0:
        raise KeyNameError("Key name must have at least 1 character")

    for char in name:
        if not char.isalnum():
            raise KeyNameError("Key name must only contain alphanumeric characters")
