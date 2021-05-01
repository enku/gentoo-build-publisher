"""Admin for Gentoo Build Publisher"""
from django.contrib import admin

from gentoo_build_publisher.models import BuildModel


@admin.register(BuildModel)
class BuildModelAdmin(admin.ModelAdmin):
    """"ModelAdmin for the BuildModel"""

    fields = ["name", "number", "submitted", "completed", "published", "keep"]
    list_display = ["name", "number", "submitted", "completed", "published", "keep"]
    list_filter = ["name", "submitted", "keep"]
    readonly_fields = [
        "name",
        "number",
        "submitted",
        "completed",
        "published",
        "task_id",
    ]

    def published(self, obj):
        return obj.published()

    published.boolean = True

    def response_change(self, request, obj):
        if "_publish" in request.POST:
            obj.publish()

        return super().response_change(request, obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return super().has_delete_permission(request, None)

        return not obj.keep
