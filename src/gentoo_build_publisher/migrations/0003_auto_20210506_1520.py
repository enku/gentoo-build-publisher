# Generated by Django 3.1.7 on 2021-05-06 15:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gentoo_build_publisher", "0002_add_purge_field_to_buildmodel"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="buildmodel",
            options={"verbose_name": "Build", "verbose_name_plural": "Builds"},
        ),
        migrations.AddIndex(
            model_name="buildmodel",
            index=models.Index(fields=["name"], name="gentoo_buil_name_c641bb_idx"),
        ),
    ]
