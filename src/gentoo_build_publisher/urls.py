"""Default urlconf for gentoo_build_publisher"""

from importlib import import_module
from importlib.metadata import entry_points

from gentoo_build_publisher.views.utils import ViewFinder

urlpatterns = ViewFinder.find()

for entry_point in entry_points().select(group="gentoo_build_publisher.apps"):
    app = entry_point.load()
    try:
        module = import_module(f"{app}.urls")
    except ImportError:
        pass
    else:
        urlpatterns.extend(getattr(module, "urlpatterns", []))
        del module

    del entry_point, app
