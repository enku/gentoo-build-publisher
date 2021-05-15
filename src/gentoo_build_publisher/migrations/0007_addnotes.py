"""Add the BuildNote model"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gentoo_build_publisher", "0006_remove_buildmodel_keep"),
    ]

    operations = [
        migrations.AlterField(
            model_name="buildmodel",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.CreateModel(
            name="BuildNote",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("note", models.TextField()),
                (
                    "build_model",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="gentoo_build_publisher.buildmodel",
                    ),
                ),
            ],
        ),
    ]
