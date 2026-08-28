from django.db import migrations


def create_members_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Members")


def remove_members_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Members").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0025_update_instruction_fort_registration"),
    ]

    operations = [
        migrations.RunPython(create_members_group, remove_members_group),
    ]