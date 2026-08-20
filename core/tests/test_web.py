"""Tests for the Smartline web interface."""
from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Activity,
    CastRate,
    Instruction,
    Player,
    Rate,
    TelegramMessage,
)

_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


class WebInterfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="kl",
            password="test-password-123",
        )
        self.player = Player.objects.create(nickname="Swettka")
        self.message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=20,
            telegram_user_id=100,
            telegram_username="swettka",
            text="+1 | деф | Swettka | Первая волна",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        self.activity = Activity.objects.create(
            player=self.player,
            telegram_message=self.message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="Первая волна",
        )

    def _login(self):
        self.client.login(username="kl", password="test-password-123")

    def test_pages_redirect_anonymous_to_login(self):
        for url_name in ["dashboard", "players", "activities", "telegram_messages", "processing_errors", "settings"]:
            response = self.client.get(reverse(url_name))
            self.assertRedirects(
                response,
                f"{reverse('login')}?next={reverse(url_name)}",
            )

    def test_login_page_available(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_pages_available_after_login(self):
        self._login()
        for url_name in ["dashboard", "players", "activities", "telegram_messages", "processing_errors", "settings"]:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200, url_name)

    def test_period_filter_works(self):
        self._login()
        old_activity = Activity.objects.create(
            player=self.player,
            telegram_message=TelegramMessage.objects.create(
                telegram_chat_id=10,
                telegram_message_id=99,
                text="+1 | деф | Swettka | старая",
                message_date=timezone.now(),
                status=TelegramMessage.Status.PROCESSED,
            ),
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="старая",
        )
        Activity.objects.filter(pk=old_activity.pk).update(
            created_at=timezone.now() - timedelta(days=45)
        )

        response = self.client.get(reverse("dashboard"), {"period": "today"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Swettka", content)
        # only today's activity counted: def hours column shows 1, not 2
        self.assertIn("<td>1</td>", content)
        self.assertNotIn("<td>2</td>", content)

    def test_player_detail_page_available_after_login(self):
        self._login()
        response = self.client.get(
            reverse("player_detail", args=[self.player.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("По дням", response.content.decode())

    def test_dashboard_shows_percent_and_columns(self):
        self._login()
        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for text in ["Ник", "Выплата, кк", "Дефал", "Фармил", "%"]:
            self.assertIn(text, content)

    def test_cast_activity_flows_through_views_and_dashboard(self):
        self._login()
        self.activity.activity_type = Activity.ActivityType.CAST
        self.activity.has_cast = True
        self.activity.payment_kk = Decimal("75.00")
        self.activity.save(update_fields=["activity_type", "has_cast", "payment_kk"])

        response = self.client.get(reverse("activities"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("CAST", response.content.decode())

        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("75", response.content.decode())

    def test_dashboard_counts_cast_activities(self):
        self._login()
        ostin = Player.objects.create(nickname="Ostin")
        # Swettka already has one DEF activity without has_cast (setUp).
        # Add DEF+CAST and a standalone CAST so Swettka ends with 2 casts.
        for message_id, text, activity_type in [
            (31, "+1 | деф | Swettka | деф+каст", Activity.ActivityType.DEF),
            (32, "+1 | каст | Swettka | каст", Activity.ActivityType.CAST),
        ]:
            message = TelegramMessage.objects.create(
                telegram_chat_id=15,
                telegram_message_id=message_id,
                telegram_user_id=100,
                telegram_username="swettka",
                text=text,
                message_date=timezone.now(),
                status=TelegramMessage.Status.PROCESSED,
            )
            Activity.objects.create(
                player=self.player,
                telegram_message=message,
                amount=Decimal("1"),
                activity_type=activity_type,
                has_cast=True,
                description=text,
            )
        # Ostin: one FARM without cast and one FARM+CAST.
        plain_farm = TelegramMessage.objects.create(
            telegram_chat_id=16,
            telegram_message_id=33,
            telegram_user_id=101,
            telegram_username="ostin",
            text="+1 | фарм | Ostin | фарм",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        Activity.objects.create(
            player=ostin,
            telegram_message=plain_farm,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.FARM,
            has_cast=False,
            description="фарм",
        )
        farm_cast = TelegramMessage.objects.create(
            telegram_chat_id=16,
            telegram_message_id=34,
            telegram_user_id=101,
            telegram_username="ostin",
            text="+1 | фарм | Ostin | фарм+каст",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        Activity.objects.create(
            player=ostin,
            telegram_message=farm_cast,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.FARM,
            has_cast=True,
            description="фарм+каст",
        )

        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        rows = {row["nickname"]: row for row in response.context["rows"]}
        # Only activities with has_cast=True are counted, regardless of type.
        self.assertEqual(rows["Swettka"]["cast_count"], 2)
        self.assertEqual(rows["Ostin"]["cast_count"], 1)
        # Existing hour columns are unchanged.
        self.assertEqual(rows["Swettka"]["total_hours"], Decimal("3"))
        self.assertEqual(rows["Ostin"]["total_hours"], Decimal("2"))
        self.assertEqual(rows["Ostin"]["farm_hours"], Decimal("2"))

    def test_excel_export_returns_xlsx_after_login(self):
        self._login()
        response = self.client.get(reverse("export_excel"), {"period": "today"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], _XLSX_CONTENT_TYPE)
        self.assertGreater(len(response.content), 0)

    def test_excel_export_requires_login(self):
        response = self.client.get(reverse("export_excel"), {"period": "today"})
        self.assertEqual(response.status_code, 302)

    def test_player_creation_and_toggle(self):
        self._login()
        response = self.client.post(reverse("players"), {"nickname": "Ostin"})
        self.assertRedirects(response, reverse("players"))
        player = Player.objects.get(nickname="Ostin")
        self.assertTrue(player.is_active)

        response = self.client.post(reverse("player_toggle", args=[player.pk]))
        self.assertRedirects(response, reverse("players"))
        player.refresh_from_db()
        self.assertFalse(player.is_active)

    def test_player_toggle_get_returns_405_and_does_not_change_state(self):
        self._login()
        player = self.player
        self.assertTrue(player.is_active)

        response = self.client.get(reverse("player_toggle", args=[player.pk]))

        self.assertEqual(response.status_code, 405)
        player.refresh_from_db()
        self.assertTrue(player.is_active)

    def test_player_delete_removes_player(self):
        self._login()
        response = self.client.post(reverse("player_delete", args=[self.player.pk]))
        self.assertRedirects(response, reverse("players"))
        self.assertFalse(Player.objects.filter(pk=self.player.pk).exists())

    def test_player_delete_cascades_activities(self):
        self._login()
        message = TelegramMessage.objects.create(
            telegram_chat_id=11,
            telegram_message_id=21,
            telegram_user_id=101,
            telegram_username="ostin",
            text="+1 | деф | Ostin | Первая волна",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        activity = Activity.objects.create(
            player=self.player,
            telegram_message=message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="Первая волна",
        )
        activity_pk = activity.pk

        response = self.client.post(reverse("player_delete", args=[self.player.pk]))

        self.assertRedirects(response, reverse("players"))
        self.assertFalse(Player.objects.filter(pk=self.player.pk).exists())
        self.assertFalse(Activity.objects.filter(pk=activity_pk).exists())

    def test_players_page_has_delete_button_with_confirm(self):
        self._login()
        response = self.client.get(reverse("players"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # форма удаления с CSRF-токеном
        self.assertIn("players/delete/", content)
        self.assertIn("csrfmiddlewaretoken", content)
        # кнопка удаления открывает подтверждение: класс delete-btn + data-player-name
        self.assertIn('class="btn delete-btn"', content)
        self.assertIn(f'data-player-name="{self.player.nickname}"', content)

    def test_player_delete_requires_login(self):
        response = self.client.post(reverse("player_delete", args=[self.player.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_settings_shows_rates_section(self):
        self._login()
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Тарифы за DEF", content)
        self.assertIn("Тарифы за каст", content)

    def test_settings_add_form_hidden_by_default(self):
        self._login()
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('id="defAddForm"', content)
        self.assertIn('id="castAddForm"', content)
        # Toggle buttons use a non-inline data attribute hook (no inline JS).
        self.assertIn(
            '<button type="button" class="btn" data-toggle-form="defAddForm">',
            content,
        )
        self.assertIn(
            '<button type="button" class="btn" data-toggle-form="castAddForm">',
            content,
        )
        self.assertNotIn("onclick=", content)
        self.assertRegex(content, r'id="defAddForm"[^>]*\shidden')
        self.assertRegex(content, r'id="castAddForm"[^>]*\shidden')

    def test_settings_add_rate(self):
        self._login()
        response = self.client.post(
            reverse("settings"),
            {
                "add_rate": "1",
                "start_time": "08:00",
                "end_time": "16:00",
                "rate_kk": "75.00",
            },
        )
        self.assertRedirects(response, reverse("settings"))
        rate = Rate.objects.get(start_time=time(8, 0), end_time=time(16, 0))
        self.assertEqual(rate.rate_kk, Decimal("75.00"))
        self.assertTrue(rate.active)
        self.assertEqual(rate.order, 0)

    def test_settings_edit_rate(self):
        self._login()
        # The 0013_seed_default_rates migration inserts default rates; clear
        # them so the count assertion below checks only this test's data.
        Rate.objects.all().delete()
        rate = Rate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("100"),
        )

        response = self.client.get(reverse("settings") + f"?edit={rate.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="edit_rate"', response.content.decode())

        response = self.client.post(
            reverse("settings"),
            {
                "edit_rate": str(rate.pk),
                "start_time": "09:00",
                "end_time": "17:00",
                "rate_kk": "80",
            },
        )
        self.assertRedirects(response, reverse("settings"))

        rate.refresh_from_db()
        self.assertEqual(rate.start_time, time(9, 0))
        self.assertEqual(rate.end_time, time(17, 0))
        self.assertEqual(rate.rate_kk, Decimal("80"))
        self.assertEqual(Rate.objects.count(), 1)

    def test_settings_add_cast_rate(self):
        self._login()
        response = self.client.post(
            reverse("settings"),
            {
                "add_cast_rate": "1",
                "start_time": "08:00",
                "end_time": "16:00",
                "rate_kk": "75.00",
            },
        )
        self.assertRedirects(response, reverse("settings"))
        cast_rate = CastRate.objects.get(
            start_time=time(8, 0), end_time=time(16, 0)
        )
        self.assertEqual(cast_rate.rate_kk, Decimal("75.00"))
        self.assertTrue(cast_rate.active)
        self.assertEqual(cast_rate.order, 0)

    def test_settings_edit_cast_rate(self):
        self._login()
        # The 0018_seed_cast_rates_from_rate migration seeds CastRate rows;
        # clear them so the count assertion below checks only this test's data.
        CastRate.objects.all().delete()
        cast_rate = CastRate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("100"),
        )

        response = self.client.get(reverse("settings") + f"?edit_cast={cast_rate.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="edit_cast_rate"', response.content.decode())

        response = self.client.post(
            reverse("settings"),
            {
                "edit_cast_rate": str(cast_rate.pk),
                "start_time": "09:00",
                "end_time": "17:00",
                "rate_kk": "80",
            },
        )
        self.assertRedirects(response, reverse("settings"))

        cast_rate.refresh_from_db()
        self.assertEqual(cast_rate.start_time, time(9, 0))
        self.assertEqual(cast_rate.end_time, time(17, 0))
        self.assertEqual(cast_rate.rate_kk, Decimal("80"))
        self.assertEqual(CastRate.objects.count(), 1)

    def test_settings_delete_cast_rate(self):
        self._login()
        # The 0018_seed_cast_rates_from_rate migration seeds CastRate rows;
        # clear them so the count assertion below checks only this test's data.
        CastRate.objects.all().delete()
        cast_rate = CastRate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("100"),
        )
        response = self.client.post(
            reverse("settings"),
            {"delete_cast_rate": str(cast_rate.pk)},
        )
        self.assertRedirects(response, reverse("settings"))
        self.assertEqual(CastRate.objects.count(), 0)

    def test_settings_delete_rate(self):
        self._login()
        # The 0013_seed_default_rates migration seeds default Rate rows;
        # clear them so the count assertion below checks only this test's data.
        Rate.objects.all().delete()
        rate = Rate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("100"),
        )
        response = self.client.post(
            reverse("settings"),
            {"delete_rate": str(rate.pk)},
        )
        self.assertRedirects(response, reverse("settings"))
        self.assertEqual(Rate.objects.count(), 0)

    def test_instructions_list_table(self):
        self._login()
        instr = Instruction.objects.create(
            slug="how-to", title="Test Instruction", content="Body"
        )
        response = self.client.get(reverse("instructions"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Test Instruction", content)
        self.assertIn(
            reverse("instruction_detail", args=[instr.pk]), content
        )
        self.assertNotIn(
            reverse("instruction_edit", args=[instr.pk]), content
        )

    def test_instructions_add_creates_and_redirects(self):
        self._login()
        count_before = Instruction.objects.count()
        response = self.client.post(
            reverse("instructions"), {"action": "add"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Instruction.objects.count(), count_before + 1)
        instr = Instruction.objects.latest("id")
        self.assertEqual(instr.title, "Новая инструкция")
        self.assertTrue(instr.slug.startswith("instruction"))

    def test_instructions_edit_saves(self):
        self._login()
        instr = Instruction.objects.create(
            slug="x", title="Old", content="Old body"
        )
        response = self.client.post(
            reverse("instruction_edit", args=[instr.pk]),
            {"slug": "x", "title": "New", "content": "Body"},
        )
        self.assertRedirects(
            response, reverse("instructions") + "?saved=1"
        )
        instr.refresh_from_db()
        self.assertEqual(instr.title, "New")
        self.assertEqual(instr.content, "Body")
        self.assertEqual(instr.updated_by, self.user)

    def test_instructions_delete(self):
        self._login()
        instr = Instruction.objects.create(
            slug="del-me", title="X", content="c"
        )
        response = self.client.post(
            reverse("instructions"),
            {"action": "delete", "pk": instr.pk},
        )
        self.assertRedirects(response, reverse("instructions"))
        self.assertFalse(Instruction.objects.filter(pk=instr.pk).exists())

    def test_instruction_edit_404(self):
        self._login()
        response = self.client.get(
            reverse("instruction_edit", args=[999999])
        )
        self.assertEqual(response.status_code, 404)
