from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "test"

USE_TZ = True

BUILD_PUBLISHER = {
    "JENKINS_BASE_URL": "http://jenkins.invalid/job/Gentoo",
    "JENKINS_API_KEY": "jenkins-key",
    "JENKINS_USER": "jenkins-user",
}

INSTALLED_APPS = ["django.contrib.contenttypes", "gentoo_build_publisher"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
