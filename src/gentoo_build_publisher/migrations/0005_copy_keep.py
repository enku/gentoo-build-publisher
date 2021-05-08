from django.db import migrations


def copy_keep(apps, schema_editor):
    BuildModel = apps.get_model("gentoo_build_publisher", "BuildModel")
    KeptBuild = apps.get_model("gentoo_build_publisher", "KeptBuild")

    for build_model in BuildModel.objects.filter(keep=True):
        kept_build, _ = KeptBuild.objects.get_or_create(build_model=build_model)


class Migration(migrations.Migration):

    dependencies = [
        ("gentoo_build_publisher", "0004_keptbuild"),
    ]

    operations = [migrations.RunPython(copy_keep)]
