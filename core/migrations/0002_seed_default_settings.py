"""Seed default settings for Smartline."""
from django.conf import settings
from django.db import migrations


def seed_default_settings(apps, schema_editor):
    Setting = apps.get_model("core", "Setting")
    Setting.objects.get_or_create(
        key="def_hourly_rate",
        defaults={
            "value": str(settings.DEF_HOURLY_RATE),
            "description": "Ставка оплаты за час DEF",
        },
    )


def remove_default_settings(apps, schema_editor):
    Setting = apps.get_model("core", "Setting")
    Setting.objects.filter(key="def_hourly_rate").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_default_settings,
            reverse_code=remove_default_settings,
        ),
    ]
