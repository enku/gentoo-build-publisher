"""
View for gbp
"""
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import MachineInfo


def index(request: HttpRequest) -> HttpResponse:
    """Index view"""
    machines = [MachineInfo(i) for i in BuildDB.list_machines()]

    return render(request, "gentoo_build_publisher/index.html", {"machines": machines})
