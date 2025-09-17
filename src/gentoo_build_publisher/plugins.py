"""Plugin interface for Gentoo Build Publisher

Plugins register themselves under the group "gentoo_build_publisher.plugins". The entry
point should be a dictionary adhering to the PluginDef specification. For example:


    plugin = {
        "name": "gbp-helloworld",
        "version": "0.1.0",
        "description":"Hello World!"
    }

"""

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import NotRequired, TypedDict


class PluginCheckDef(TypedDict, total=False):
    """A plugin check declaration"""

    name: str
    path: str


@dataclass(kw_only=True, frozen=True, slots=True)
class Plugin:
    """A GBP Plugin"""

    # pylint: disable=too-many-instance-attributes

    name: str
    app: str | None
    version: str = "?"
    description: str = ""
    graphql: str | None
    urls: str | None
    priority: int = 10
    checks: PluginCheckDef | None = None

    def __hash__(self) -> int:
        return hash(self.app)


class PluginDef(TypedDict):
    """Plugin definition

    Plugins use this to define themselves. This gets loaded as an entry point and then
    converted to a Plugin dataclass.  Why do we need both? I just prefer working with
    dataclasses than dicts but the definition seems to work better as a primitive (no
    need to import anything).
    """

    name: str

    app: NotRequired[str | None]
    """Dotted path to Django app config"""

    version: NotRequired[str]
    """Plugin version specifier"""

    description: NotRequired[str]
    """Natural text description of the plugin"""

    graphql: NotRequired[str]
    """The module that contains the graphql definitions.

    Plugins are not required to expose any GraphQL types
    """

    urls: NotRequired[str]
    """Dotted path to module containing urlpatterns"""

    checks: NotRequired[PluginCheckDef]
    """Any `gbp check` check functions that the plugin provides"""

    priority: NotRequired[int]


def get_plugins() -> list[Plugin]:
    """Return the list of registered plugins"""
    eps = entry_points()
    gbp = "gentoo_build_publisher"

    return sorted(
        {ep2plugin(ep) for ep in eps.select(group=f"{gbp}.plugins")},
        key=lambda p: p.priority,
    )


def ep2plugin(ep: EntryPoint) -> Plugin:
    """Convert EntryPoint to a Plugin"""
    data: PluginDef = ep.load()

    return Plugin(
        name=data["name"],
        app=data.get("app", None),
        version=data.get("version", "?"),
        description=data.get("description", ""),
        graphql=data.get("graphql"),
        urls=data.get("urls"),
        checks=data.get("checks"),
        priority=data.get("priority", 10),
    )
