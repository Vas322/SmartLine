"""Tests for the month filter on the dashboard and player detail pages."""
import re
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.forms import PeriodForm
from core.forms.activity import get_month_choices
from core.models import Activity, Player, TelegramMessage


def _months_ago_str(months: int) -> str:
    """Return 'YYYY-MM' for `months` months before the current one."""
    d = timezone.localdate()
    m = d.month - months
    y = d.year
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


class GetMonthChoicesTests(TestCase):
    """Tests for get_month_choices()."""

    def test_returns_13_months_including_current(self):
        choices = get_month_choices()
        self.assertEqual(len(choices), 13)

    def test_last_choice_is_current_month(self):
        choices = get_month_choices()
        now = timezone.localdate()
        self.assertEqual(choices[-1][0], now.strftime("%Y-%m"))
        self.assertTrue(choices[-1][1].endswith(f" {now.year}"))

    def test_first_choice_is_12_months_ago(self):
        choices = get_month_choices()
        self.assertEqual(choices[0][0], _months_ago_str(12))

    def test_choices_are_ordered_oldest_to_newest(self):
        choices = get_month_choices()
        keys = [key for key, _ in choices]
        self.assertEqual(keys, sorted(keys))

    def test_label_format(self):
        choices = get_month_choices()
        for _, label in choices:
            self.assertRegex(label, r"^[А-ЯЁ][а-яё]+ \d{4}$")


class PeriodFormMonthTests(TestCase):
    """Tests for PeriodForm when period == 'month' with a selected month."""

    def test_selected_month_used_in_date_range(self):
        month = _months_ago_str(2)
        year, mm = month.split("-")
        form = PeriodForm(data={"period": "month", "month": month})
        self.assertTrue(form.is_valid())
        start, end = form.get_date_range()
        first = date(int(year), int(mm), 1)
        # last day of the selected month
        next_month = date(int(year), int(mm) % 12 + 1, 1) if int(mm) < 12 else date(int(year) + 1, 1, 1)
        last = next_month - timezone.timedelta(days=1)
        self.assertEqual(start.date(), first)
        self.assertEqual(end.date(), last)

    def test_no_month_uses_current_month(self):
        form = PeriodForm(
            data={"period": "month"},
            initial={"period": "month", "month": timezone.localdate().strftime("%Y-%m")},
        )
        start, end = form.get_date_range()
        today = timezone.localdate()
        self.assertEqual(start.date(), today.replace(day=1))
        next_month = today.replace(day=28) + timezone.timedelta(days=4)
        self.assertEqual(end.date(), next_month.replace(day=1) - timezone.timedelta(days=1))


class MonthFilterWebTests(TestCase):
    """End-to-end tests for the month filter in views and templates."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.client.login(username="kl", password="test-password-123")

    def _make_message(self, chat_id, msg_id, user_id):
        return TelegramMessage.objects.create(
            telegram_chat_id=chat_id,
            telegram_message_id=msg_id,
            telegram_user_id=user_id,
            telegram_username="test",
            text="+1 | деф | Test | Волна",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )

    def _create_activity(self, player, month_str, day):
        """Create an activity on a fixed day of the selected month."""
        year, mm = month_str.split("-")
        tm = TelegramMessage.objects.create(
            telegram_chat_id=100,
            telegram_message_id=int(f"{int(year)}{int(mm)}{day:02d}"),
            telegram_user_id=500,
            telegram_username="test",
            text="+1 | деф | Test | Волна",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        return Activity.objects.create(
            player=player,
            telegram_message=tm,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            payment_kk=Decimal("75.00"),
            created_at=timezone.make_aware(
                timezone.datetime(int(year), int(mm), day, 12, 0)
            ),
        )

    def test_dashboard_context_has_applied_month(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["applied_period"], "month")
        self.assertEqual(
            response.context["applied_month"],
            timezone.localdate().strftime("%Y-%m"),
        )

    def test_dashboard_selected_month_in_context_and_dates(self):
        month = _months_ago_str(1)
        year, mm = month.split("-")
        response = self.client.get(reverse("dashboard"), {"period": "month", "month": month})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["applied_period"], "month")
        self.assertEqual(response.context["applied_month"], month)
        self.assertEqual(response.context["date_from"].date(), date(int(year), int(mm), 1))

    def test_dashboard_reset_button_and_month_select_present(self):
        response = self.client.get(reverse("dashboard"))
        content = response.content.decode()
        self.assertIn('id="month-select-wrapper"', content)
        self.assertIn('id="reset-filter"', content)

    def test_player_detail_selected_month_in_context(self):
        player = Player.objects.create(nickname="Тестер")
        month = _months_ago_str(1)
        response = self.client.get(
            reverse("player_detail", args=[player.pk]),
            {"period": "month", "month": month},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["applied_period"], "month")
        self.assertEqual(response.context["applied_month"], month)

    def test_player_detail_back_link_keeps_month(self):
        player = Player.objects.create(nickname="Тестер")
        month = _months_ago_str(1)
        response = self.client.get(
            reverse("player_detail", args=[player.pk]),
            {"period": "month", "month": month},
        )
        content = response.content.decode()
        back_href = content.split("К фортам", 1)[0]
        self.assertIn("period=month", back_href)
        self.assertIn(f"month={month}", back_href)

    def test_player_detail_back_link_keeps_custom_period(self):
        player = Player.objects.create(nickname="Тестер")
        response = self.client.get(
            reverse("player_detail", args=[player.pk]),
            {"period": "custom", "date_from": "2026-08-01", "date_to": "2026-08-30"},
        )
        content = response.content.decode()
        back_href = content.split("К фортам", 1)[0]
        self.assertIn("period=custom", back_href)
        self.assertIn("date_from=2026-08-01", back_href)
        self.assertIn("date_to=2026-08-30", back_href)

    def test_player_detail_reset_and_month_select_present(self):
        player = Player.objects.create(nickname="Тестер")
        response = self.client.get(reverse("player_detail", args=[player.pk]))
        content = response.content.decode()
        self.assertIn('id="month-select-wrapper"', content)
        self.assertIn('id="reset-filter"', content)

    def test_player_detail_sort_link_keeps_month(self):
        player = Player.objects.create(nickname="Тестер")
        month = _months_ago_str(1)
        response = self.client.get(
            reverse("player_detail", args=[player.pk]),
            {"period": "month", "month": month},
        )
        content = response.content.decode()
        m = re.search(r'href="(\?period=[^"]*)"', content)
        self.assertIsNotNone(m, "sort link not found")
        sort_link = m.group(1).replace("&amp;", "&")
        self.assertIn("period=month", sort_link)
        self.assertIn(f"month={month}", sort_link)
        self.assertIn("&sort=", sort_link)

    def test_dashboard_player_link_preserves_filter(self):
        """Dashboard player links carry the player-link class for filter JS."""
        player = Player.objects.create(nickname="Тестер")
        self._create_activity(player, _months_ago_str(0), 15)
        response = self.client.get(reverse("dashboard"))
        content = response.content.decode()
        self.assertIn("player-link", content)
