"""App-specific settings for Gentoo Build Publisher"""
from django.conf import settings as django_settings

USER_SETTINGS = getattr(django_settings, "BUILD_PUBLISHER", None)


DEFAULTS = {
    "JENKINS_ARTIFACT_NAME": "build.tar.gz",
    "JENKINS_API_KEY": "JENKINS_API_KEY_REQUIRED",
    "JENKINS_BASE_URL": "http://jenkins/Gentoo",
    "JENKINS_USER": "jenkins",
    "HOME_DIR": "/var/lib/gentoo-build-publisher",
}


class GBPSettings:
    """Pattern for app settings"""
    def __init__(self, user_settings=None, defaults=None):
        self.user_settings = user_settings or {}
        self.defaults = defaults or {}

    def __getattr__(self, attr):
        if attr not in self.defaults.keys():
            raise AttributeError(attr)

        try:
            value = self.user_settings[attr]
        except KeyError:
            value = self.defaults[attr]

        value = self.validate_setting(attr, value)
        setattr(self, attr, value)

        return value

    def validate_setting(self, _attr, value):  # pylint: disable=no-self-use
        """Validate a settings"""
        # For now we don't do any special validation
        return value


settings = GBPSettings(USER_SETTINGS, DEFAULTS)
