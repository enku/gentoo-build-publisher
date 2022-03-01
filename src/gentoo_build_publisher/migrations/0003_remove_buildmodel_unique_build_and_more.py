# Generated by Django 4.0.2 on 2022-02-27 16:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gentoo_build_publisher", "0002_alter_buildmodel_number"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="buildmodel",
            name="unique_build",
        ),
        migrations.RenameField(
            model_name="buildmodel",
            old_name="number",
            new_name="build_id",
        ),
        migrations.AddConstraint(
            model_name="buildmodel",
            constraint=models.UniqueConstraint(
                fields=("machine", "build_id"), name="unique_build"
            ),
        ),
    ]