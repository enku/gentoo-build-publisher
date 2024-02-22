from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gentoo_build_publisher", "0003_remove_buildmodel_unique_build_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiKey",
            fields=[
                (
                    "apikey",
                    models.CharField(max_length=256, primary_key=True, serialize=False),
                ),
                ("name", models.CharField(max_length=128, unique=True)),
                ("last_used", models.DateTimeField(default=None, null=True)),
            ],
        ),
    ]
