from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gentoo_build_publisher", "0003_remove_buildmodel_unique_build_and_more")
    ]

    operations = [
        migrations.CreateModel(
            name="ApiKey",
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
                ("apikey", models.BinaryField()),
                ("name", models.CharField(max_length=128, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_used", models.DateTimeField(default=None, null=True)),
            ],
        )
    ]
