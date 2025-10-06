"""AppsConfigs for Gentoo Build Publisher"""

import importlib

from django.apps import AppConfig


class GentooBuildPublisherConfig(AppConfig):
    """AppConfig for Gentoo Build Publisher"""

    name = "gentoo_build_publisher.django.gentoo_build_publisher"
    verbose_name = "Gentoo Build Publisher"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        signals = importlib.import_module(f"{self.name}.signals")
        signals.init()
