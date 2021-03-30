"""
Django models for Gentoo Build Publisher
"""
from typing import Any, Dict

from django.db import models

from gentoo_build_publisher.conf import settings
from gentoo_build_publisher.types import Build, Jenkins, Storage


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

    def __init__(self, *args, **kwargs):
        if "storage" in kwargs:
            self.storage: Storage = kwargs.pop("storage")
        else:
            self.storage = Storage.from_settings(settings)

        if "jenkins" in kwargs:
            self.jenkins: Jenkins = kwargs.pop("jenkins")
        else:
            self.jenkins = Jenkins.from_settings(settings)

        super().__init__(*args, **kwargs)

        self.build = Build(self.name, self.number)

    def __repr__(self) -> str:
        name = self.name
        number = self.number
        name = type(self).__name__

        return f"{name}(name={name!r}, number={number})"

    def __str__(self) -> str:
        return str(self.build)

    def publish(self):
        """Publish the Build"""
        self.storage.publish(self.build)

    def delete(self, using=None, keep_parents=False):
        # The reason to call super().delete() before removing the directories is if for
        # some reason super().delete() fails we don't want to delete the directories.
        super().delete(using=using, keep_parents=keep_parents)

        self.storage.delete_build(self.build)

    def as_dict(self) -> Dict[str, Any]:
        """Convert build instance attributes to a dict"""
        return {
            "name": self.name,
            "number": self.number,
            "published": self.storage.published(self.build),
            "url": self.jenkins.build_url(self.build),
        }
