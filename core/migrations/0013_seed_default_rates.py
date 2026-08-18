"""Seed default hourly rates and drop the obsolete def_hourly_rate setting."""
from datetime import time
from decimal import Decimal

from django.db import migrations

DEFAULT_RATES = [
    {
        "start_time": time(0, 1),
        "end_time": time(8, 0),
        "rate_kk": Decimal("100"),
        "order": 1,
    },
    {
        "start_time": time(8, 1),
        "end_time": time(16, 0),
        "rate_kk": Decimal("75"),
        "order": 2,
    },
    {
        "start_time": time(16, 1),
        "end_time": time(0, 0),  # wrap past midnight; stored as time(0, 0)
        "rate_kk": Decimal("50"),
        "order": 3,
    },
]


def seed_default_rates(apps, schema_editor):
    Rate = apps.get_model("core", "Rate")
    for rate in DEFAULT_RATES:
        Rate.objects.get_or_create(
            start_time=rate["start_time"],
            end_time=rate["end_time"],
            defaults={
                "rate_kk": rate["rate_kk"],
                "order": rate["order"],
            },
        )


def remove_default_rates(apps, schema_editor):
    Rate = apps.get_model("core", "Rate")
    for rate in DEFAULT_RATES:
        Rate.objects.filter(
            start_time=rate["start_time"],
            end_time=rate["end_time"],
            rate_kk=rate["rate_kk"],
            order=rate["order"],
        ).delete()


def delete_def_hourly_rate_setting(apps, schema_editor):
    Setting = apps.get_model("core", "Setting")
    Setting.objects.filter(key="def_hourly_rate").delete()


def do_nothing(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_rate_activity_payment_kk_activity_wave_start_time"),
    ]

    operations = [
        migrations.RunPython(seed_default_rates, remove_default_rates),
        migrations.RunPython(delete_def_hourly_rate_setting, do_nothing),
    ]