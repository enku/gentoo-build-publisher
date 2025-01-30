"""AppsConfigs for Gentoo Build Publisher"""

from django.apps import AppConfig


class GentooBuildPublisherConfig(AppConfig):
    """AppConfig for Gentoo Build Publisher"""

    name = "gentoo_build_publisher"
    verbose_name = "Gentoo Build Publisher"
    default_auto_field = "django.db.models.BigAutoField"
