"""Default urlconf for gentoo_build_publisher"""

from gentoo_build_publisher.views import ViewFinder

urlpatterns = ViewFinder.find()
