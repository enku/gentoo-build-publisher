"""So we don't have to do import django; django.setup()"""

import django
from django.apps import apps


if not apps.ready:
    django.setup()
