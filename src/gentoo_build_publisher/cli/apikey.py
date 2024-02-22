"""gbpcli apikey subcommand"""

import argparse
import secrets
from functools import partial

from django.db import IntegrityError, transaction
from gbpcli import GBP, Console

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
    return 0


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
            return 1
        except KeyNameError as error:
            console.err.print(str(error.args[0]))
            return 2

    console.out.print(key)
    return 0


def create_api_key() -> str:
    """Create an API key"""
    settings = Settings.from_environ()

    return secrets.token_urlsafe(settings.API_KEY_LENGTH)


def create_root_key() -> str:
    """Create a key for encrypting API keys"""
    return create_secret_key().decode("ascii")


def save_api_key(api_key: str, name: str) -> ApiKey:
    """Save the given api_key to the repository with the given name"""
    validate_key_name(name)
    name = name.lower()
    settings = Settings.from_environ()
    encode = partial(str.encode, encoding="ascii")

    return ApiKey.objects.create(
        name=name, apikey=encrypt(encode(api_key), encode(settings.API_KEY_KEY))
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
