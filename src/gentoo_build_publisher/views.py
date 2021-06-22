"""
View for gbp
"""
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gentoo_build_publisher.build import Build, Content
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.diff import dirdiff
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.tasks import publish_build, pull_build


@require_POST
@csrf_exempt
def publish(_request: HttpRequest, build_name: str, build_number: int) -> JsonResponse:
    """View to publish a build"""
    buildman = BuildMan(Build(name=build_name, number=build_number))

    if buildman.pulled():
        buildman.publish()
    else:
        publish_build.delay(build_name, build_number)

    response = buildman.as_dict()
    response["error"] = None

    return JsonResponse(response)


@require_POST
@csrf_exempt
def pull(_request: HttpRequest, build_name: str, build_number: int) -> JsonResponse:
    """View to pull a new build"""
    pull_build.delay(build_name, build_number)
    response = BuildMan(Build(name=build_name, number=build_number)).as_dict()
    response["error"] = None

    return JsonResponse(response)


def show_build(
    _request: HttpRequest, build_name: str, build_number: int
) -> JsonResponse:
    """View details of a build"""
    build = Build(name=build_name, number=build_number)
    buildman = BuildMan(build)
    response = buildman.as_dict()
    response["error"] = None

    status_code = 200 if buildman.db else 404

    return JsonResponse(response, status=status_code)


@require_POST
@csrf_exempt
def delete(_request: HttpRequest, build_name: str, build_number: int) -> JsonResponse:
    """View to delete a build"""
    build = Build(name=build_name, number=build_number)
    buildman = BuildMan(build)

    if buildman.db:
        buildman.delete()
        return JsonResponse({"deleted": True, "error": None})

    return JsonResponse({"error": "Not found"}, status=404)


def latest(_request: HttpRequest, build_name: str) -> JsonResponse:
    """View to return the latest build for a machine"""
    builds = BuildDB.builds(name=build_name, completed__isnull=False)

    try:
        build_db = next(builds)
    except StopIteration:
        return JsonResponse(
            {"error": "No completed builds exist with that name"}, status=404
        )

    response = BuildMan(build_db).as_dict()
    response["error"] = None

    return JsonResponse(response)


def list_builds(_request: HttpRequest, build_name: str) -> JsonResponse:
    """View to return the list of builds with the given machine"""
    builds = list(BuildDB.builds(name=build_name, completed__isnull=False))
    builds.sort(key=lambda i: i.number)

    if not builds:
        return JsonResponse(
            {"error": "No completed builds exist with that name", "builds": []},
            status=404,
        )

    return JsonResponse(
        {
            "error": None,
            "builds": [BuildMan(i).as_dict() for i in builds],
        }
    )


def logs(_request: HttpRequest, build_name: str, build_number: int) -> HttpResponse:
    """View to return the Jenkins build logs for a given build"""
    build = Build(name=build_name, number=build_number)
    build_db = BuildDB.get(build)

    if build_db is None or build_db.logs is None:
        return HttpResponse("Not Found", content_type="text/plain", status=404)

    return HttpResponse(build_db.logs, content_type="text/plain")


def diff_builds(
    _request: HttpRequest, build_name: str, left: int, right: int
) -> JsonResponse:
    """View to show the diff between two builds for the given machines"""
    left_build = BuildMan(Build(name=build_name, number=left))

    if not left_build.db:
        return JsonResponse({"error": "left build not found"}, status=404)

    right_build = BuildMan(Build(name=build_name, number=right))

    if not right_build.db:
        return JsonResponse({"error": "right build not found"}, status=404)

    left_path = left_build.storage_build.get_path(Content.BINPKGS)
    right_path = right_build.storage_build.get_path(Content.BINPKGS)

    items = dirdiff(str(left_path), str(right_path))

    return JsonResponse(
        {
            "error": None,
            "diff": {
                "builds": [left_build.as_dict(), right_build.as_dict()],
                "items": list(i.tuple() for i in items),
            },
        }
    )


def list_machines(_request: HttpRequest) -> JsonResponse:
    """List the machines and build counts"""
    machines = BuildDB.list_machines()
    machines.sort(key=lambda i: i.name)

    return JsonResponse({"error": None, "machines": [i.as_dict() for i in machines]})
