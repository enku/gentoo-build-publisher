"""Admin for Gentoo Build Publisher"""
from __future__ import annotations

from django.contrib import admin

from gentoo_build_publisher.models import BuildModel, BuildNote, KeptBuild
from gentoo_build_publisher.publisher import get_publisher


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

    fields = [
        "machine",
        "build_id",
        "built",
        "submitted",
        "completed",
        "published",
        "keep",
    ]
    inlines = [BuildNoteInline]
    list_display = [
        "machine",
        "build_id",
        "built",
        "submitted",
        "completed",
        "published",
        "keep",
        "note",
    ]
    list_filter = ["machine", "submitted", KeepListFilter]
    readonly_fields = [
        "machine",
        "build_id",
        "built",
        "submitted",
        "completed",
        "published",
        "keep",
    ]

    def published(self, obj: BuildModel) -> bool:
        """Return the admin published field"""
        publisher = get_publisher()

        return publisher.published(obj.record())

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
        publisher = get_publisher()

        if "_publish" in request.POST:
            publisher.publish(obj.record())

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
        publisher = get_publisher()

        if obj is None:
            return super().has_delete_permission(request, None)

        return not (KeptBuild.keep(obj) or publisher.published(obj.record()))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["keep"] = KeptBuild.objects.filter(
            build_model__id=object_id
        ).exists()

        return super().change_view(
            request, object_id, form_url=form_url, extra_context=extra_context
        )
