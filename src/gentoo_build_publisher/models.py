"""
Django models for Gentoo Build Publisher
"""
from typing import Any, Dict, Optional

from django.db import models

from gentoo_build_publisher import Build, Jenkins, Settings, Storage


class BuildModel(models.Model):
    """Django persistance for Build objects"""

    # The Jenkins build name
    name = models.CharField(max_length=255, db_index=True)

    # The Jenkins build number
    number = models.PositiveIntegerField()

    # when this build was submitted to GBP
    submitted = models.DateTimeField()

    # When this build's publish task completed
    completed = models.DateTimeField(null=True)

    # The build's task id
    task_id = models.UUIDField(null=True)

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        constraints = [
            models.UniqueConstraint(fields=["name", "number"], name="unique_build")
        ]

    def __init__(
        self,
        *args,
        jenkins: Optional[Jenkins] = None,
        settings: Optional[Settings] = None,
        storage: Optional[Storage] = None,
        **kwargs,
    ):
        self.jenkins: Jenkins
        self.storage: Storage

        settings = settings or Settings.from_environ()
        self.jenkins = jenkins or Jenkins.from_settings(settings)
        self.storage = storage or Storage.from_settings(settings)

        super().__init__(*args, **kwargs)

        self.build = Build(self.name, self.number)

    def __repr__(self) -> str:
        name = self.name
        number = self.number
        class_name = type(self).__name__

        return f"{class_name}(name={name!r}, number={number})"

    def __str__(self) -> str:
        return str(self.build)

    def publish(self):
        """Publish the Build"""
        self.storage.publish(self.build, self.jenkins)

    def delete(self, using=None, keep_parents=False):
        # The reason to call super().delete() before removing the directories is if for
        # some reason super().delete() fails we don't want to delete the directories.
        super().delete(using=using, keep_parents=keep_parents)

        self.storage.delete_build(self.build)

    @classmethod
    def purge(cls, name: str, keep: int):
        """Purge all but the last `keep` builds.

        Make sure to keep the published build.
        """
        published = None
        builds = cls.objects.filter(name=name)

        # First do the easy thing and get all the keep recent ones
        to_keep = [*builds.order_by("-submitted").values_list("id", flat=True)[:keep]]

        for build_model in builds.exclude(id__in=to_keep):
            if not build_model.storage.published(build_model.build):
                build_model.delete()
            else:
                published = build_model

        if published:
            num_kept = builds.count()
            if num_kept > keep:
                builds.exclude(id=published.id).order_by("submitted")[0].delete()

    def as_dict(self) -> Dict[str, Any]:
        """Convert build instance attributes to a dict"""
        return {
            "name": self.name,
            "number": self.number,
            "published": self.storage.published(self.build),
            "url": self.jenkins.build_url(self.build),
        }
