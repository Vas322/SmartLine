"""Clear local test data, keep config (Instruction, Rate, Setting) and users."""
from django.core.management.base import BaseCommand

from core.models import Activity, Player, ProcessingError, TelegramMessage


class Command(BaseCommand):
    help = "Delete test Activity/TelegramMessage/ProcessingError/Player data."

    def handle(self, *args, **options):
        # Order matters: Activity FK to TelegramMessage is PROTECT, and
        # ProcessingError OneToOne to TelegramMessage is PROTECT.
        n_activity = Activity.objects.count()
        n_error = ProcessingError.objects.count()
        n_message = TelegramMessage.objects.count()
        n_player = Player.objects.count()

        Activity.objects.all().delete()
        ProcessingError.objects.all().delete()
        TelegramMessage.objects.all().delete()
        Player.objects.all().delete()

        self.stdout.write(
            f"Cleared: Activity={n_activity}, ProcessingError={n_error}, "
            f"TelegramMessage={n_message}, Player={n_player}"
        )