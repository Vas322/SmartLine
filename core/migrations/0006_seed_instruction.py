"""Seed the first instruction for Smartline."""
from django.db import migrations


INSTRUCTION_CONTENT = """Запись активности на форте

Сообщение должно начинаться с + и содержать 4 части, разделённые между собой:

+<время> <разделитель> <тип> <разделитель> <ник> <разделитель> <описание>

1. Время - сколько часов: 1, 2, 0,5 (через запятую) или 0.5 (через точку).
2. Тип - деф (оплачивается) или фарм (учитывается, но не оплачивается). Регистр не важен: ДЕФ, DEF, ФАРМ - всё подойдёт.
3. Ник - твой точный ник в игре (только буквы и цифры, как в L2 Astrios).
4. Описание - любой текст (волна, замок, комментарий).

Разделители (любой, с пробелами или без): | (вертикальная черта), - (дефис, удобнее с русской раскладки), – или — (тире).

Примеры (все правильные):
+1 - деф - Swettka - Первая волна
+0,5 | деф | Swettka | Вторая волна
+2–фарм–Ostin–две волны
+1 ДЕФ Swettka описание

Важно:
- Обычные сообщения без + в статистику не попадают.
- Одно сообщение = одна запись активности.
- Ник должен совпадать с зарегистрированным; при ошибке КЛ получит уведомление.
- Не дублируй сообщение: одно и то же уже учтено не будет повторно.
"""


def create_instruction(apps, schema_editor):
    Instruction = apps.get_model("core", "Instruction")
    Instruction.objects.update_or_create(
        slug="how-to-write-activity",
        defaults={
            "title": "Запись активности на форте",
            "content": INSTRUCTION_CONTENT,
        },
    )


def remove_instruction(apps, schema_editor):
    Instruction = apps.get_model("core", "Instruction")
    Instruction.objects.filter(slug="how-to-write-activity").delete()


class Migration(migrations.Migration):

    dependencies = [("core", "0005_instruction")]

    operations = [
        migrations.RunPython(create_instruction, remove_instruction),
    ]