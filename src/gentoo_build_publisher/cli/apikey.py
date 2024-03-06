"""gbpcli apikey subcommand"""

import argparse
import secrets
from enum import IntEnum
from functools import partial

from django.db import IntegrityError, transaction
from gbpcli import GBP
from gbpcli.render import format_timestamp
from gbpcli.types import Console
from rich import box
from rich.table import Table

import gentoo_build_publisher._django_setup  # pylint: disable=unused-import
from gentoo_build_publisher.models import ApiKey
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.utils import create_secret_key, encrypt

ROOT_KEY_NAME = "root"


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """gbp apikey subcommand handler"""
    match args.action:
        case "create":
            return create_action(args, console)
        case "delete":
            return delete_action(args, console)
        case "list":
            return list_action(args, console)

    console.err.print(f"Unknown action: {args.action}")
    return StatusCode.UNKNOWN


def create_action(args: argparse.Namespace, console: Console) -> int:
    """handle the "create" action"""
    if args.name == ROOT_KEY_NAME:
        key = create_root_key()
    else:
        key = create_api_key()

        try:
            with transaction.atomic():
                save_api_key(key, args.name)
        except IntegrityError:
            console.err.print("An API key with that name already exists.")
            return StatusCode.NAME_EXISTS
        except KeyNameError as error:
            console.err.print(str(error.args[0]))
            return StatusCode.INVALID_NAME

    console.out.print(key)
    return StatusCode.SUCCESS


def list_action(args: argparse.Namespace, console: Console) -> int:
    """handle the "list" action"""
    keys_query = ApiKey.objects.all()

    if not keys_query.exists():
        console.out.print("No API keys registered.")
        return StatusCode.SUCCESS

    table = Table(box=box.ROUNDED, style="box")
    table.add_column("Name", header_style="header")
    table.add_column("Last Used", header_style="header")

    for record in keys_query:
        table.add_row(
            record.name,
            format_timestamp(record.last_used) if record.last_used else "Never",
        )

    console.out.print(table)

    return StatusCode.SUCCESS


def delete_action(args: argparse.Namespace, console: Console) -> int:
    """handle the "delete" action"""
    name = args.name.lower()

    try:
        ApiKey.objects.get(name=name).delete()
    except ApiKey.DoesNotExist:
        console.err.print("No key exists with that name.")
        return StatusCode.NAME_DOES_NOT_EXIST

    return StatusCode.SUCCESS


def parse_args(parser: argparse.ArgumentParser) -> None:
    """Set up parser arguments"""
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparser = subparsers.add_parser(
        "create", description="Create an API key with the given name"
    )
    subparser.add_argument("name", type=str, help="Unique name for the key")

    subparsers.add_parser("list", description="List registered API keys")

    subparser = subparsers.add_parser(
        "delete", description="Deliete the API key with the given name"
    )
    subparser.add_argument("name", type=str, help="Name of the key")


def create_api_key() -> str:
    """Create an API key"""
    settings = Settings.from_environ()

    return secrets.token_hex(settings.API_KEY_LENGTH)


def create_root_key() -> str:
    """Create a key for encrypting API keys"""
    return create_secret_key().decode("ascii")


def save_api_key(api_key: str, name: str) -> ApiKey:
    """Save the given api_key to the repository with the given name"""
    from django.conf import settings  # pylint: disable=import-outside-toplevel

    validate_key_name(name)
    name = name.lower()
    encode = partial(str.encode, encoding="ascii")

    return ApiKey.objects.create(
        name=name, apikey=encrypt(encode(api_key), encode(settings.SECRET_KEY))
    )


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


class StatusCode(IntEnum):
    """Process exit codes"""

    SUCCESS = 0
    NAME_EXISTS = 1
    INVALID_NAME = 2
    NAME_DOES_NOT_EXIST = 3
    UNKNOWN = 255
