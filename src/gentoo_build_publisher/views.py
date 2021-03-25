"""
View for gbp
"""
import datetime
from typing import Optional

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gentoo_build_publisher.models import Build
from gentoo_build_publisher.tasks import publish_build


def now(timestamp: Optional[datetime.datetime] = None) -> datetime.datetime:
    """Return timezone-aware datetime"""
    if timestamp is None:
        timestamp = datetime.datetime.utcnow()

    return timestamp.replace(tzinfo=datetime.timezone.utc)


@require_POST
@csrf_exempt
def publish(_request: HttpRequest, build_name: str, build_number: int):
    """Jenkins call-back to publish a new build"""
    build = Build.objects.get_or_create(
        build_name=build_name, build_number=build_number, defaults={"submitted": now()}
    )[0]

    publish_build.delay(build.pk)
    response = {"buildId": build.pk, "error": None}

    return JsonResponse(response)
