"""
View for gbp
"""
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gentoo_build_publisher.models import BuildModel
from gentoo_build_publisher.tasks import publish_build


@require_POST
@csrf_exempt
def publish(_request: HttpRequest, build_name: str, build_number: int) -> JsonResponse:
    """Jenkins call-back to publish a new build"""
    build_model, _ = BuildModel.objects.get_or_create(
        name=build_name,
        number=build_number,
        defaults={"submitted": timezone.now()},
    )

    publish_build.delay(build_model.id)
    response = build_model.as_dict()
    response["error"] = None

    return JsonResponse(response)


@require_POST
@csrf_exempt
def delete(_request: HttpRequest, build_name: str, build_number: int) -> JsonResponse:
    """View to delete a build"""
    build_model = get_object_or_404(BuildModel, name=build_name, number=build_number)

    build_model.delete()

    return JsonResponse({"deleted": True, "error": None})
