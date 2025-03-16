"""Django urlconf for gentoo_build_publisher"""

from importlib import import_module
from itertools import chain

from django.urls import URLPattern

from gentoo_build_publisher.plugins import Plugin, get_plugins


def plugin_urlpatterns(plugin: Plugin) -> list[URLPattern]:
    """Return the urlpatterns defined in the given plugin"""
    if plugin.urls:
        try:
            module = import_module(plugin.urls)
            return getattr(module, "urlpatterns", [])
        except ImportError:
            pass
    return []


urlpatterns = list(chain(*(plugin_urlpatterns(plugin) for plugin in get_plugins())))
