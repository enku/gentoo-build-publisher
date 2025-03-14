"""Default urlconf for gentoo_build_publisher"""

from importlib import import_module

from django.urls import URLPattern

from gentoo_build_publisher.plugins import Plugin, get_plugins
from gentoo_build_publisher.views.utils import ViewFinder

urlpatterns = ViewFinder.find()


def plugin_urlpatterns(plugin: Plugin) -> list[URLPattern]:
    """Return the urlpatterns defined in the given plugin"""
    if not plugin.urls:
        return []

    try:
        module = import_module(plugin.urls)
    except ImportError:
        return []

    return getattr(module, "urlpatterns", [])


def init() -> None:
    """Initialize plugin urls"""
    for plugin in get_plugins():
        urlpatterns.extend(plugin_urlpatterns(plugin))  # pragma: no cover


init()
