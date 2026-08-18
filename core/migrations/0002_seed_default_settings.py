"""Seed default settings for Smartline.

The legacy ``def_hourly_rate`` setting is obsolete: hourly DEF payment is now
derived from the ``core.Rate`` model. The functions are kept as no-ops so the
migration history stays stable for databases that already ran this migration.
"""
from django.db import migrations


def seed_default_settings(apps, schema_editor):
    # def_hourly_rate is no longer seeded; rates live in core.Rate.
    pass


def remove_default_settings(apps, schema_editor):
    pass


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