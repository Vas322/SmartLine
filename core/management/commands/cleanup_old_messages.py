"""Management command to clean up old regular Telegram messages."""
import logging

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core.models import TelegramMessage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete old regular Telegram messages older than N days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=14,
            help="Delete messages older than this many days (default: 14).",
        )

    def handle(self, *args, **options):
        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)

        deleted_count, _ = TelegramMessage.objects.filter(
            created_at__lt=cutoff,
        ).exclude(
            Q(text__istartswith="+")
            | Q(text__istartswith="рега")
            | Q(text__istartswith="регистрация")
        ).filter(
            activities__isnull=True,
            registration__isnull=True,
        ).delete()

        logger.info(
            "Cleaned %d old regular messages (older than %d days)",
            deleted_count,
            days,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Cleaned {deleted_count} old regular messages (older than {days} days).")
        )