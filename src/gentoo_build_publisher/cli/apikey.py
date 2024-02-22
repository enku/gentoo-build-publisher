"""gbpcli apikey subcommand"""

import argparse
import secrets

from gbpcli import GBP, Console

import gentoo_build_publisher._django_setup  # pylint: disable=unused-import
from gentoo_build_publisher.models import ApiKey
from gentoo_build_publisher.settings import Settings


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """gbp apikey subcommand handler"""
    match args.action:
        case "create":
            console.out.print(save_api_key(create_api_key(), args.name).apikey)
    return 0


def create_api_key() -> str:
    """Create an API key"""
    settings = Settings.from_environ()

    return secrets.token_urlsafe(settings.API_KEY_LENGTH)


def save_api_key(api_key: str, name: str) -> ApiKey:
    """Save the given api_key to the repository with the given name"""
    return ApiKey.objects.create(name=name.lower(), apikey=api_key)
