"""Default urlconf for gentoo_build_publisher"""

from gentoo_build_publisher.views.utils import ViewFinder

urlpatterns = ViewFinder.find()
