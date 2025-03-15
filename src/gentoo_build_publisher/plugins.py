"""Plugin interface for Gentoo Build Publisher

Plugins register themselves under the group "gentoo_build_publisher.plugins", but
"gentoo_build_publisher.apps" is kept for backwards compatibility
"""

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import NotRequired, Optional, TypedDict


@dataclass(kw_only=True, frozen=True, slots=True)
class Plugin:
    """A GBP Plugin"""

    name: str
    app: str
    description: str = ""
    graphql: Optional[str]
    urls: Optional[str]

    def __hash__(self) -> int:
        return hash(self.app)


class PluginDef(TypedDict):
    """Plugin definition

    Plugins use this to define themselves. This gets loaded as an entry point and then
    convertd to a Plugin dataclass?  Why do we need both? I just prefer working with
    dataclasses than dicts but the definition seems to work better as a primitive.
    """

    name: str
    app: str

    description: NotRequired[str]
    """Natural text description of the plugin"""

    graphql: NotRequired[str]
    """The module that contains the graphql definitions.

    Plugins are not required to expose any GraphQL types
    """

    urls: NotRequired[str]
    """Dotted path to module containing urlpatterns"""


def get_plugins() -> list[Plugin]:
    """Return the list of registered plugins"""
    eps = entry_points()
    gbp = "gentoo_build_publisher"

    return list(
        {ep2plugin(ep) for ep in eps.select(group=f"{gbp}.plugins")}
        | {ep2plugin(ep) for ep in eps.select(group=f"{gbp}.apps")}
    )


def ep2plugin(ep: EntryPoint) -> Plugin:
    """Convert EntryPoint to a Plugin"""
    data: str | PluginDef = ep.load()

    if isinstance(data, str):
        return Plugin(name=ep.name, app=data, graphql=None, urls=f"{data}.urls")
    if isinstance(data, dict):
        return Plugin(
            name=data["name"],
            app=data["app"],
            description=data.get("description", ""),
            graphql=data.get("graphql"),
            urls=data.get("urls"),
        )

    raise ValueError(f"{data!r} is not a dict or string")
