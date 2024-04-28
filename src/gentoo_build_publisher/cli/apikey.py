"""gbpcli apikey subcommand"""

import argparse
import secrets
from enum import IntEnum

from gbpcli import GBP
from gbpcli.render import format_timestamp
from gbpcli.subcommands import completers as comp
from gbpcli.types import Console
from rich import box
from rich.table import Table

from gentoo_build_publisher import publisher
from gentoo_build_publisher.records import RecordNotFound
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import ApiKey
from gentoo_build_publisher.utils import InvalidIdentifier, create_secret_key, time

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
        name = args.name.lower()

        if name in [key.name for key in publisher.repo.api_keys.list()]:
            console.err.print("An API key with that name already exists.")
            return StatusCode.NAME_EXISTS

        try:
            save_api_key(ApiKey(name=name, key=key, created=time.localtime()))
        except InvalidIdentifier as error:
            console.err.print(str(error.args[0]))
            return StatusCode.INVALID_NAME

    console.out.print(key)
    return StatusCode.SUCCESS


def list_action(args: argparse.Namespace, console: Console) -> int:
    """handle the "list" action"""
    keys = publisher.repo.api_keys.list()

    if not keys:
        console.out.print("No API keys registered.")
        return StatusCode.SUCCESS

    table = Table(box=box.ROUNDED, style="box")
    table.add_column("Name", header_style="header")
    table.add_column("Last Used", header_style="header")

    for api_key in keys:
        table.add_row(
            api_key.name,
            (
                format_timestamp(time.localtime(api_key.last_used))
                if api_key.last_used
                else "Never"
            ),
        )

    console.out.print(table)

    return StatusCode.SUCCESS


def delete_action(args: argparse.Namespace, console: Console) -> int:
    """handle the "delete" action"""
    name = args.name.lower()

    try:
        publisher.repo.api_keys.delete(name)
    except RecordNotFound:
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
    comp.set(
        subparser.add_argument("name", type=str, help="Name of the key"), key_names
    )


def create_api_key() -> str:
    """Create an API key"""
    settings = Settings.from_environ()

    return secrets.token_hex(settings.API_KEY_LENGTH)


def create_root_key() -> str:
    """Create a key for encrypting API keys"""
    return create_secret_key().decode("ascii")


def save_api_key(api_key: ApiKey) -> None:
    """Save the given api_key to the repository with the given name"""
    publisher.repo.api_keys.save(api_key)


class StatusCode(IntEnum):
    """Process exit codes"""

    SUCCESS = 0
    NAME_EXISTS = 1
    INVALID_NAME = 2
    NAME_DOES_NOT_EXIST = 3
    UNKNOWN = 255


def key_names(
    *,
    prefix: str,
    action: argparse.Action,
    parser: argparse.ArgumentParser,
    parsed_args: argparse.Namespace,
) -> list[str]:
    """Return list of existing key names"""
    # pylint: disable=unused-argument
    return [api_key.name for api_key in publisher.repo.api_keys.list()]
