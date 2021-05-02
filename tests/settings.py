"""Settings for tests"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "test"

USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "gentoo_build_publisher.apps.GentooBuildPublisherConfig",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
