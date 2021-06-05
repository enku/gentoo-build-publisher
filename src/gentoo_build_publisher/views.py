"""
View for gbp
"""
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gentoo_build_publisher.diff import dirdiff
from gentoo_build_publisher.models import BuildLog, BuildModel
from gentoo_build_publisher.tasks import publish_build, pull_build


@require_POST
@csrf_exempt
def publish(_request: HttpRequest, build_name: str, build_number: int) -> JsonResponse:
    """View to publish a build"""
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
def pull(_request: HttpRequest, build_name: str, build_number: int) -> JsonResponse:
    """View to pull a new build"""
    build_model, _ = BuildModel.objects.get_or_create(
        name=build_name,
        number=build_number,
        defaults={"submitted": timezone.now()},
    )

    pull_build.delay(build_model.id)
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


def latest(_request: HttpRequest, build_name: str) -> JsonResponse:
    """View to return the latest build for a machine"""
    builds = BuildModel.objects.filter(
        name=build_name, completed__isnull=False
    ).order_by("-submitted")

    if builds.count() == 0:
        return JsonResponse(
            {"error": "No completed builds exist with that name"}, status=404
        )

    response = builds[0].as_dict()
    response["error"] = None

    return JsonResponse(response)


def list_builds(_request: HttpRequest, build_name: str) -> JsonResponse:
    """View to return the list of builds with the given machine"""
    builds = BuildModel.objects.filter(
        name=build_name, completed__isnull=False
    ).order_by("number")

    if builds.count() == 0:
        return JsonResponse(
            {"error": "No completed builds exist with that name", "builds": []},
            status=404,
        )

    return JsonResponse({"error": None, "builds": [i.as_dict() for i in builds]})


def logs(_request: HttpRequest, build_name: str, build_number: int) -> HttpResponse:
    """View to return the Jenkins build logs for a given build"""
    build_log = get_object_or_404(
        BuildLog, build_model__name=build_name, build_model__number=build_number
    )

    return HttpResponse(build_log.logs, content_type="text/plain")


def diff_builds(
    _request: HttpRequest, build_name: str, left: int, right: int
) -> JsonResponse:
    """View to show the diff between two builds for the given machines"""
    left_build = get_object_or_404(BuildModel, name=build_name, number=left)
    right_build = get_object_or_404(BuildModel, name=build_name, number=right)

    left_path = left_build.storage.get_path(
        left_build.build, left_build.build.Content.BINPKGS
    )
    right_path = right_build.storage.get_path(
        right_build.build, right_build.build.Content.BINPKGS
    )

    items = dirdiff(str(left_path), str(right_path))

    return JsonResponse(
        {
            "error": None,
            "diff": {
                "builds": [left_build.as_dict(), right_build.as_dict()],
                "items": list(items),
            },
        }
    )
