"""Admin for Gentoo Build Publisher"""
from django.contrib import admin

from gentoo_build_publisher.models import BuildModel


class KeepListFilter(admin.SimpleListFilter):
    """Custom list filter for the "keep" attribute"""

    title = "keep"
    parameter_name = "keep"

    def lookups(self, request, model_admin):
        return (
            ("true", "Yes"),
            ("false", "No"),
        )

    def queryset(self, request, queryset):
        """Return the filtered queryset."""
        if self.value() == "true":
            return queryset.filter(keptbuild__isnull=False)

        if self.value() == "false":
            return queryset.filter(keptbuild__isnull=True)

        return queryset


@admin.register(BuildModel)
class BuildModelAdmin(admin.ModelAdmin):
    """"ModelAdmin for the BuildModel"""

    fields = ["name", "number", "submitted", "completed", "published", "keep"]
    list_display = ["name", "number", "submitted", "completed", "published", "keep"]
    list_filter = ["name", "submitted", KeepListFilter]
    readonly_fields = [
        "name",
        "number",
        "submitted",
        "completed",
        "published",
        "task_id",
        "keep",
    ]

    def published(self, obj):
        """Return the admin published field"""
        return obj.published()

    published.boolean = True

    @admin.display(ordering="keptbuild")
    def keep(self, obj):
        """Return the admin keep field"""
        return obj.keep

    keep.boolean = True

    def response_change(self, request, obj):
        if "_publish" in request.POST:
            obj.publish()

        if "_keep" in request.POST:
            obj.keep = not obj.keep

        return super().response_change(request, obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return super().has_delete_permission(request, None)

        return not obj.keep
