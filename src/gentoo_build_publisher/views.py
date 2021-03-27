"""
View for gbp
"""
from typing import Optional

from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gentoo_build_publisher.models import Build
from gentoo_build_publisher.tasks import publish_build


@require_POST
@csrf_exempt
def publish(_request: HttpRequest, build_name: str, build_number: int) -> JsonResponse:
    """Jenkins call-back to publish a new build"""
    build = Build.objects.get_or_create(
        build_name=build_name,
        build_number=build_number,
        defaults={"submitted": timezone.now()},
    )[0]

    publish_build.delay(build.pk)
    response = build.as_dict()
    response["error"] = None

    return JsonResponse(response)


@require_POST
@csrf_exempt
def delete(_request: HttpRequest, build_name: str, build_number: int) -> JsonResponse:
    """View to delete a build"""
    build = get_object_or_404(Build, build_name=build_name, build_number=build_number)

    build.delete()

    response = {"deleted": True, "error": None}

    return JsonResponse(response)
