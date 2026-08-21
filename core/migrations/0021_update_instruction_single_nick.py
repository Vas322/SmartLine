"""Update the activity instruction for single-nick binding: each player writes only for themselves."""
from django.db import migrations
from django.db.models import Q


INSTRUCTION_CONTENT = """Запись активности на форте

Отправляй сообщение ТОЛЬКО за себя. Формат:

+время на волне | тип | ник | время начала волны | описание

Поля:
1. Время — сколько часов: 1, 2, 0,5 (через запятую) или 0.5 (через точку).
2. Тип — деф (оплачивается), фарм (учитывается, но не оплачивается) или каст. Можно комбинировать: деф+каст. Регистр не важен.
3. Ник — ТВОЙ ник, один, только буквы (рус/англ) и цифры. Не пиши за других и не указывай несколько ников.
4. Время начала волны — ОБЯЗАТЕЛЬНО. Формат HH.MM или HH:MM (например, 11.56 или 11:56).
5. Описание — любой текст (волна, замок, комментарий). Необязательно.

Пример: +1 | деф+каст | Swettka | 11.56 | Деф и каст

Если допустил ошибку — отредактируй своё сообщение по шаблону.
"""

previous_content = {}


def update_instruction_content(apps, schema_editor):
    Instruction = apps.get_model("core", "Instruction")
    global previous_content
    previous_content = dict(
        Instruction.objects.filter(
            Q(slug="how-to-write-activity") | Q(title="Запись активности на форте")
        ).values_list("pk", "content")
    )
    Instruction.objects.filter(
        Q(slug="how-to-write-activity") | Q(title="Запись активности на форте")
    ).update(content=INSTRUCTION_CONTENT)


def revert_instruction_content(apps, schema_editor):
    Instruction = apps.get_model("core", "Instruction")
    if not previous_content:
        return
    for pk, content in previous_content.items():
        Instruction.objects.filter(pk=pk).update(content=content)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_player_telegram_user_id_and_more"),
    ]

    operations = [
        migrations.RunPython(update_instruction_content, revert_instruction_content),
    ]