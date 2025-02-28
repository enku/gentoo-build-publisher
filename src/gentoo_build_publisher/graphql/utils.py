"""graphql sub-package utilities"""

from __future__ import annotations

import datetime as dt
import importlib.metadata
from dataclasses import dataclass, replace
from functools import wraps
from typing import Any, Callable, TypeAlias

import ariadne
from graphql import GraphQLError, GraphQLResolveInfo

from gentoo_build_publisher import publisher, utils
from gentoo_build_publisher.records import RecordNotFound
from gentoo_build_publisher.settings import Settings

Info: TypeAlias = GraphQLResolveInfo
Resolver: TypeAlias = Callable[..., Any]

SCHEMA_GROUP = "gentoo_build_publisher.graphql_schema"


class UnauthorizedError(GraphQLError):
    """Raised when the request is not authorized to execute a query"""


@dataclass(frozen=True, slots=True)
class Error:
    """Return Type for errors"""

    message: str

    @classmethod
    def from_exception(cls, exception: Exception) -> Error:
        """Convert exception into an Error"""
        return cls(f"{exception.__class__.__name__}: {exception}")


def require_apikey(fn: Resolver) -> Resolver:
    """Require an API key in the HTTP request.

    This decorator is to be used by GraphQL resolvers that require authentication. The
    decorator checks that the HTTP request has a Basic Auth header and that the header's
    name and secret matches an ApiKey record. If it does then the record's last_used
    field is updated and the decorated resolver is called and returned. If not then a
    GraphQL error is raised.
    """

    @wraps(fn)
    def wrapper(obj: Any, info: Info, **kwargs: Any) -> Any:
        """wrapper function"""
        try:
            auth = info.context["request"].headers["Authorization"]
            name, key = utils.parse_basic_auth_header(auth)
            api_key = publisher.repo.api_keys.get(name=name.lower())
            if api_key.key == key:
                api_key = replace(api_key, last_used=dt.datetime.now(tz=dt.UTC))
                publisher.repo.api_keys.save(api_key)
                return fn(obj, info, **kwargs)
        except (KeyError, ValueError, RecordNotFound):
            pass

        raise UnauthorizedError(f"Unauthorized to resolve {info.path.key}")

    return wrapper


maybe_require_apikey = utils.conditionally(
    lambda: Settings.from_environ().API_KEY_ENABLE, require_apikey
)


def load_schema() -> tuple[list[str], list[ariadne.ObjectType]]:
    """Load all GraphQL schema for Gentoo Build Publisher

    This function loads all entry points for the group
    "gentoo_build_publisher.graphql_schema" and returns them all into a single list.
    This list can be used to make_executable_schema()
    """
    all_type_defs: list[str] = []
    all_resolvers = []

    for entry_point in importlib.metadata.entry_points(group=SCHEMA_GROUP):
        module = entry_point.load()
        all_type_defs.append(module.type_defs)
        all_resolvers.extend(module.resolvers)

    return (all_type_defs, all_resolvers)
