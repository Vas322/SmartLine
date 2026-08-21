"""Update the activity instruction: add cast/recast activity type and combos."""
from django.db import migrations


INSTRUCTION_CONTENT = """Сообщение обязательно начинается с +:

+время на волне | тип | ники | время начала волны | описание

Примеры:

+1 | деф | Swettka | 11.56 | Первая волна
+0,5 | фарм | Ostin, Pocomaxa | 23:10
+2 | ДЕФ | Pocomaxa | 11.56
+1 | деф+каст | Swettka | 11.56 | Деф и каст
+1 | каст | Swettka | 11.56

Что указывать:

Время — 1, 2, 0,5 или 0.5.

Тип — деф, фарм или каст. Поддерживаются русское/английское написание и любой регистр. Синонимы каста: каст, cast, перекаст, recast.

Ники — один или несколько через запятую. Только буквы и цифры.

Начало волны — обязательно, формат HH.MM или HH:MM.

Описание — необязательно, но желательно.

Правила:

Разделители: |, -, – или —. Пробелы между частями разделителем не считаются.

Несколько ников указываются через запятую — каждому будет создана отдельная запись.
Один основной тип = одно сообщение. Деф и фарм вместе запрещены — отправьте два сообщения.

Каст можно объединить с дефом или фармом: деф+каст, фарм каст.

Оплата:

Деф оплачивается по времени начала волны. Фарм учитывается, но не оплачивается. Каст оплачивается отдельно по тарифу и при комбинации деф+каст сумма складывается. Если волна пересекает границу тарифов, оплата рассчитывается пропорционально.

Ошибки:

Если сообщение составлено неправильно, бот покажет ошибку прямо под ним. Исправьте сообщение редактированием — бот автоматически пересчитает запись без создания дубля.
"""

previous_content = {}


def update_instruction_content(apps, schema_editor):
    Instruction = apps.get_model("core", "Instruction")
    global previous_content
    previous_content = dict(
        Instruction.objects.filter(slug="how-to-write-activity").values_list("pk", "content")
    )
    Instruction.objects.filter(slug="how-to-write-activity").update(
        content=INSTRUCTION_CONTENT
    )


def revert_instruction_content(apps, schema_editor):
    Instruction = apps.get_model("core", "Instruction")
    if not previous_content:
        return
    for pk, content in previous_content.items():
        Instruction.objects.filter(pk=pk).update(content=content)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_seed_cast_rates_from_rate"),
    ]

    operations = [
        migrations.RunPython(update_instruction_content, revert_instruction_content),
    ]