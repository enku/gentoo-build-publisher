"""The Gentoo Build Publisher Django template tags subpackage"""

from django.conf import settings

# This are the links that are displayed in the footer of every page. They can be
# overridden in the Django setting FOOTER_LINKS
FOOTER_LINKS: dict[str, str] = getattr(settings, "BUILD_PUBLISHER", {}).get(
    "FOOTER_LINKS",
    {
        "Blog": "https://lunarcowboy.com/tag/gentoo-build-publisher.html",
        "GitHub": "https://github.com/enku/gentoo-build-publisher",
        "PyPI": "https://pypi.org/project/gentoo-build-publisher/",
        "Gentoo Packages": "https://packages.gentoo.org/",
        "Gentoo News Items": "https://www.gentoo.org/support/news-items/",
    },
)
