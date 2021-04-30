"""Admin for Gentoo Build Publisher"""
from django.contrib import admin

from gentoo_build_publisher.models import BuildModel


class BuildModelAdmin(admin.ModelAdmin):
    """"ModelAdmin for the BuildModel"""

    list_display = ["name", "number", "submitted", "completed", "keep"]
    list_filter = ["name", "submitted", "keep"]
    readonly_fields = ["name", "number", "submitted", "completed", "task_id"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return super().has_delete_permission(request, None)

        return not obj.keep


admin.site.register(BuildModel, BuildModelAdmin)
