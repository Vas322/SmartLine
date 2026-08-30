from django.db import migrations
from django.db.models import F


def backfill(apps, schema_editor):
    TelegramMessage = apps.get_model("core", "TelegramMessage")
    TelegramMessage.objects.filter(original_text="").update(original_text=F("text"))


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_activity_edited_at_telegrammessage_edit_fields"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
