"""Default urlconf for gentoo_build_publisher"""

from importlib import import_module

from django.urls import URLPattern

from gentoo_build_publisher import utils
from gentoo_build_publisher.views.utils import ViewFinder

urlpatterns = ViewFinder.find()


def app_urlpatterns(app: str) -> list[URLPattern]:
    """Return the urlpatterns defined in the given app"""
    try:
        module = import_module(f"{app}.urls")
    except ImportError:
        return []

    return getattr(module, "urlpatterns", [])


utils.for_each_app(lambda app: urlpatterns.extend(app_urlpatterns(app)))
