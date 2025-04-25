"""Default urlconf for gentoo_build_publisher"""

from .views.utils import ViewFinder

urlpatterns = ViewFinder.find()
