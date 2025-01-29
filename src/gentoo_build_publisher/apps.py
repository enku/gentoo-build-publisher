"""AppsConfigs for Gentoo Build Publisher"""

from importlib import import_module

from django.apps import AppConfig


class GentooBuildPublisherConfig(AppConfig):
    """AppConfig for Gentoo Build Publisher"""

    name = "gentoo_build_publisher"
    verbose_name = "Gentoo Build Publisher"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        signals = import_module("gentoo_build_publisher.signals")
        signals.dispatcher.emit("ready")
