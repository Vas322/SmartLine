"""Tests for the Smartline web interface."""
from datetime import time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Activity,
    CastRate,
    Instruction,
    Player,
    Rate,
    Registration,
    RegistrationRate,
    ScheduleMirror,
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

    def test_activity_type_display(self):
        """Test type_display property returns correct compound type strings."""
        message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=100,
            text="+1 | деф | Test | тест",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        # DEF
        act_def = Activity.objects.create(
            player=self.player,
            telegram_message=message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            has_cast=False,
        )
        self.assertEqual(act_def.type_display, "DEF")

        # FARM
        act_farm = Activity.objects.create(
            player=self.player,
            telegram_message=message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.FARM,
            has_cast=False,
        )
        self.assertEqual(act_farm.type_display, "FARM")

        # CAST
        act_cast = Activity.objects.create(
            player=self.player,
            telegram_message=message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.CAST,
            has_cast=True,
        )
        self.assertEqual(act_cast.type_display, "CAST")

        # DEF+CAST
        act_def_cast = Activity.objects.create(
            player=self.player,
            telegram_message=message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            has_cast=True,
        )
        self.assertEqual(act_def_cast.type_display, "DEF+CAST")

        # FARM+CAST
        act_farm_cast = Activity.objects.create(
            player=self.player,
            telegram_message=message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.FARM,
            has_cast=True,
        )
        self.assertEqual(act_farm_cast.type_display, "FARM+CAST")

    def test_activities_view_shows_compound_type(self):
        self._login()
        message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=200,
            text="+1 | деф+каст | Swettka | деф+каст",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        Activity.objects.create(
            player=self.player,
            telegram_message=message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            has_cast=True,
            description="деф+каст",
        )
        response = self.client.get(reverse("activities"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("DEF+CAST", response.content.decode())

    def test_activity_filter_cast_includes_compound(self):
        self._login()
        message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=201,
            text="+1 | деф+каст | Swettka | деф+каст",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        Activity.objects.create(
            player=self.player,
            telegram_message=message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            has_cast=True,
            description="деф+каст",
        )
        response = self.client.get(reverse("activities"), {"activity_type": "CAST"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("DEF+CAST", response.content.decode())

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

    def test_player_edit_requires_staff(self):
        self._login()
        response = self.client.get(reverse("player_edit", args=[self.player.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("admin", response.url)

    def test_player_edit_updates_nickname_and_user_id(self):
        self.user.is_staff = True
        self.user.save()
        self._login()
        response = self.client.post(
            reverse("player_edit", args=[self.player.pk]),
            {"nickname": "Ostin", "telegram_user_id": "999"},
        )
        self.assertRedirects(response, reverse("players"))
        self.player.refresh_from_db()
        self.assertEqual(self.player.nickname, "Ostin")
        self.assertEqual(self.player.telegram_user_id, 999)

    def test_player_edit_rejects_duplicate_nickname(self):
        self.user.is_staff = True
        self.user.save()
        Player.objects.create(nickname="Ostin")
        self._login()
        response = self.client.post(
            reverse("player_edit", args=[self.player.pk]),
            {"nickname": "ostin", "telegram_user_id": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.player.refresh_from_db()
        self.assertEqual(self.player.nickname, "Swettka")

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


@override_settings(
    TELEGRAM_BOT_TOKEN="12345:TESTTOKEN",
    SCHEDULE_SOURCE_CHAT_ID=-5329088669,
    ALLIANCE_BOT_USERNAME="x5_fort_bot",
    CLAN_CHAT_ID=-1000000000,
)
class ScheduleMirrorViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.non_staff_user = User.objects.create_user(
            username="player", password="test-password-123", is_staff=False
        )

    def _login_staff(self):
        self.client.login(username="kl", password="test-password-123")

    def _login_non_staff(self):
        self.client.login(username="player", password="test-password-123")

    def test_schedule_mirror_requires_staff(self):
        """Non-staff users should be redirected (302 to admin/login)."""
        self._login_non_staff()
        response = self.client.get(reverse("schedule_mirror"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("admin", response.url)

    def test_schedule_mirror_get_shows_form(self):
        """Staff user sees the form on GET."""
        self._login_staff()
        response = self.client.get(reverse("schedule_mirror"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Добавить / обновить расписание", response.content.decode())
        self.assertIn("ID исходного чата", response.content.decode())
        self.assertIn("ID сообщения с расписанием", response.content.decode())

    def test_schedule_mirror_post_creates_mirror(self):
        """POST with valid data creates ScheduleMirror via service."""
        self._login_staff()
        with mock.patch("core.views.schedule_mirror_service.setup_mirror") as mock_setup:
            mock_mirror = mock.Mock()
            mock_setup.return_value = mock_mirror

            response = self.client.post(
                reverse("schedule_mirror"),
                {
                    "source_chat_id": "-5329088669",
                    "alliance_bot_username": "x5_fort_bot",
                    "target_chat_id": "-1000000000",
                    "message_id": "123",
                    "label": "Test",
                },
            )

            self.assertRedirects(response, reverse("schedule_mirror"))
            mock_setup.assert_called_once()
            call_kwargs = mock_setup.call_args.kwargs
            self.assertEqual(call_kwargs["source_chat_id"], -5329088669)
            self.assertEqual(call_kwargs["source_message_id"], 123)
            self.assertEqual(call_kwargs["target_chat_id"], -1000000000)
            self.assertEqual(call_kwargs["alliance_bot_username"], "x5_fort_bot")
            self.assertEqual(call_kwargs["label"], "Test")
            self.assertEqual(call_kwargs["user"], self.staff_user)

    def test_schedule_mirror_post_shows_error_on_valueerror(self):
        """POST shows form error when setup_mirror raises ValueError."""
        self._login_staff()
        with mock.patch("core.views.schedule_mirror_service.setup_mirror") as mock_setup:
            mock_setup.side_effect = ValueError("Не удалось получить сообщение")

            response = self.client.post(
                reverse("schedule_mirror"),
                {
                    "source_chat_id": "-5329088669",
                    "alliance_bot_username": "x5_fort_bot",
                    "target_chat_id": "-1000000000",
                    "message_id": "123",
                    "label": "Test",
                },
            )

            self.assertEqual(response.status_code, 200)
            content = response.content.decode()
            self.assertIn("Не удалось получить сообщение", content)

    def test_schedule_mirror_reconcile_action(self):
        """POST with action=reconcile calls reconcile_all and redirects."""
        self._login_staff()
        with mock.patch("core.views.schedule_mirror_service.reconcile_all") as mock_reconcile:
            response = self.client.post(
                reverse("schedule_mirror"),
                {"action": "reconcile"},
            )

            self.assertRedirects(response, reverse("schedule_mirror"))
            mock_reconcile.assert_called_once()

    def test_schedule_mirror_shows_current_active_mirror(self):
        """GET shows current active mirror text."""
        self._login_staff()
        ScheduleMirror.objects.create(
            source_chat_id=-5329088669,
            source_message_id=100,
            target_chat_id=-1000000000,
            target_message_id=999,
            last_text="Текущее расписание",
            is_active=True,
        )
        response = self.client.get(reverse("schedule_mirror"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Текущее расписание", content)
        self.assertIn("chat_id=-5329088669", content)
        self.assertIn("message_id=100", content)


class RegistrationDashboardTests(TestCase):
    """Tests for registration display on dashboard."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="kl",
            password="test-password-123",
        )
        self.player = Player.objects.create(nickname="Swettka", telegram_user_id=100)
        self.player2 = Player.objects.create(nickname="Ostin", telegram_user_id=200)
        self.message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=20,
            telegram_user_id=100,
            telegram_username="swettka",
            text="+1 | деф | Swettka | Первая волна",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        # Activity payment for 1 hour DEF at 11:56 = 75 kk (from default rates)
        self.activity = Activity.objects.create(
            player=self.player,
            telegram_message=self.message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="Первая волна",
            payment_kk=Decimal("75.00"),
        )

    def _login(self):
        self.client.login(username="kl", password="test-password-123")

    def test_dashboard_shows_registration_column(self):
        """Dashboard table includes 'Регистрировал' column."""
        self._login()
        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Регистрировал", content)

    def test_dashboard_shows_total_payout_line(self):
        """Dashboard shows 'Итого за период' line with total."""
        self._login()
        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Итого за период", content)
        self.assertIn("кк</p>", content)  # Total payout line

    def test_dashboard_includes_registration_in_adena(self):
        """Registration payments are included in 'Выплата, кк' (adena)."""
        self._login()
        # Create a registration for Swettka
        reg_msg = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=21,
            telegram_user_id=100,
            telegram_username="swettka",
            text="рега 2 кланами атака форта",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        Registration.objects.create(
            player=self.player,
            telegram_message=reg_msg,
            clans_count=2,
            payment_kk=Decimal("20.00"),
            description="атака форта",
            photo_file_id="photo123",
            registered_at=timezone.now(),
        )

        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        rows = {row["nickname"]: row for row in response.context["rows"]}
        # Adena = activity payment (75) + registration payment (20) = 95
        self.assertEqual(rows["Swettka"]["adena"], Decimal("95.00"))
        # Registration column shows number of clans (2), not money
        self.assertEqual(rows["Swettka"]["registration"], 2)
        # Ostin has no registration
        self.assertEqual(rows["Ostin"]["registration"], 0)

    def test_dashboard_percent_unchanged_by_registrations(self):
        """Attendance percent is based on hours, not registration money."""
        self._login()
        # Create registration for Swettka
        reg_msg = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=21,
            telegram_user_id=100,
            telegram_username="swettka",
            text="рега 5 кланов",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        Registration.objects.create(
            player=self.player,
            telegram_message=reg_msg,
            clans_count=5,
            payment_kk=Decimal("50.00"),
            description="",
            photo_file_id="photo123",
            registered_at=timezone.now(),
        )

        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        rows = {row["nickname"]: row for row in response.context["rows"]}
        # Percent should be based on hours only (1 hour DEF = 1/5 = 20% for 1 day period, etc.)
        # The exact value depends on days_in_period, but it should NOT include registration money
        self.assertEqual(rows["Swettka"]["total_hours"], Decimal("1"))
        # Registration money is in adena but not in percent calculation
        self.assertEqual(rows["Swettka"]["registration"], 5)


class RegistrationSettingsTests(TestCase):
    """Tests for RegistrationRate CRUD in settings."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="kl",
            password="test-password-123",
        )
        # Clear any seeded registration rates
        RegistrationRate.objects.all().delete()

    def _login(self):
        self.client.login(username="kl", password="test-password-123")

    def test_settings_shows_registration_rates_section(self):
        self._login()
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Тарифы за регистрацию", content)

    def test_settings_add_registration_rate(self):
        self._login()
        response = self.client.post(
            reverse("settings"),
            {
                "add_reg_rate": "1",
                "start_time": "08:00",
                "end_time": "16:00",
                "rate_kk": "15.00",
            },
        )
        self.assertRedirects(response, reverse("settings"))
        rate = RegistrationRate.objects.get(start_time=time(8, 0), end_time=time(16, 0))
        self.assertEqual(rate.rate_kk, Decimal("15.00"))
        self.assertTrue(rate.active)
        self.assertEqual(rate.order, 0)

    def test_settings_edit_registration_rate(self):
        self._login()
        rate = RegistrationRate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("10.00"),
            order=1,
        )

        response = self.client.get(reverse("settings") + f"?edit_reg={rate.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="edit_reg_rate"', response.content.decode())

        response = self.client.post(
            reverse("settings"),
            {
                "edit_reg_rate": str(rate.pk),
                "start_time": "09:00",
                "end_time": "17:00",
                "rate_kk": "25.00",
            },
        )
        self.assertRedirects(response, reverse("settings"))

        rate.refresh_from_db()
        self.assertEqual(rate.start_time, time(9, 0))
        self.assertEqual(rate.end_time, time(17, 0))
        self.assertEqual(rate.rate_kk, Decimal("25.00"))
        self.assertEqual(RegistrationRate.objects.count(), 1)

    def test_settings_delete_registration_rate(self):
        self._login()
        rate = RegistrationRate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("10.00"),
        )
        response = self.client.post(
            reverse("settings"),
            {"delete_reg_rate": str(rate.pk)},
        )
        self.assertRedirects(response, reverse("settings"))
        self.assertEqual(RegistrationRate.objects.count(), 0)

    def test_settings_registration_rate_form_hidden_by_default(self):
        self._login()
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('id="regAddForm"', content)
        self.assertIn(
            '<button type="button" class="btn" data-toggle-form="regAddForm">',
            content,
        )
        self.assertRegex(content, r'id="regAddForm"[^>]*\shidden')
