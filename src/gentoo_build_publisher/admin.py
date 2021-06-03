"""Admin for Gentoo Build Publisher"""
# pylint: disable=no-self-use
from django.contrib import admin

from gentoo_build_publisher.models import BuildModel, BuildNote, KeptBuild


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


class BuildNoteInline(admin.TabularInline):
    """TabularInline for Build notes"""
    model = BuildNote


@admin.register(BuildModel)
class BuildModelAdmin(admin.ModelAdmin):
    """ModelAdmin for the BuildModel"""

    fields = ["name", "number", "submitted", "completed", "published", "keep"]
    inlines = [BuildNoteInline]
    list_display = [
        "name",
        "number",
        "submitted",
        "completed",
        "published",
        "keep",
        "note",
    ]
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
        return KeptBuild.keep(obj)

    keep.boolean = True

    @admin.display(ordering="buildnote")
    def note(self, obj):
        """Return whether this build has a note"""
        try:
            BuildNote.objects.get(build_model=obj)
            return True
        except BuildNote.DoesNotExist:
            return False

    note.boolean = True

    def response_change(self, request, obj):
        if "_publish" in request.POST:
            obj.publish()

        if "_keep" in request.POST:
            try:
                kept_build = KeptBuild.objects.get(build_model=obj)
                kept_build.delete()
            except KeptBuild.DoesNotExist:
                KeptBuild.objects.create(build_model=obj)

        return super().response_change(request, obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return super().has_delete_permission(request, None)

        return not (KeptBuild.keep(obj) or obj.published())

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["keep"] = KeptBuild.objects.filter(
            build_model__id=object_id
        ).exists()

        return super().change_view(
            request, object_id, form_url=form_url, extra_context=extra_context
        )
