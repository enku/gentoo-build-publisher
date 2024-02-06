"""Gentoo Build Publisher"""

# pylint: disable=invalid-name
from celery import Celery

default_app_config = "gentoo_build_publisher.apps.GentooBuildPublisherConfig"

celery = Celery("gentoo_build_publisher")
celery.config_from_object("django.conf:settings", namespace="CELERY")
celery.autodiscover_tasks()
