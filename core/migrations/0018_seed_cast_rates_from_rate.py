"""Seed CastRate rows from the existing Rate table.

CastRate has no fallback to Rate in the payment calculation, so it must be
populated initially by copying every Rate row (same time interval, KK rate,
active flag and ordering).
"""
from django.db import migrations


def seed_cast_rates(apps, schema_editor):
    Rate = apps.get_model("core", "Rate")
    CastRate = apps.get_model("core", "CastRate")
    for rate in Rate.objects.all().order_by("id"):
        CastRate.objects.get_or_create(
            start_time=rate.start_time,
            end_time=rate.end_time,
            defaults={
                "rate_kk": rate.rate_kk,
                "active": rate.active,
                "order": rate.order,
            },
        )


def do_nothing(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_castrate_activity_has_cast_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_cast_rates, do_nothing),
    ]