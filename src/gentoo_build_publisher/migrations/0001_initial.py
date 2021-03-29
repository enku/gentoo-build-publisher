from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BuildModel",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255)),
                ("number", models.PositiveIntegerField()),
                ("submitted", models.DateTimeField()),
                ("completed", models.DateTimeField(null=True)),
                ("task_id", models.UUIDField(null=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="buildmodel",
            constraint=models.UniqueConstraint(
                fields=("name", "number"), name="unique_build"
            ),
        ),
    ]
