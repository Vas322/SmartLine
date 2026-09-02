"""Tests for outgoing messages (web -> Telegram) feature."""
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import OutgoingMessage, TelegramMessage, TelegramSettings, TelegramTopic
from telegram_bot.bot import TelegramAPIError

_GROUP_CHAT_ID = -1001234567890


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class OutgoingMessagesViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        members_group, _ = Group.objects.get_or_create(name="Members")
        self.member = User.objects.create_user(
            username="member", password="test-password-123", is_staff=False
        )
        self.member.groups.add(members_group)
        self.group = TelegramSettings.objects.create(
            name="Основная группа",
            group_chat_id=_GROUP_CHAT_ID,
            is_active=True,
        )
        TelegramTopic.objects.create(name="FORTS", thread_id=12, is_active=True, group=self.group)
        TelegramTopic.objects.create(name="FARM", thread_id=13, is_active=True, group=self.group)
        self.incoming = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=20,
            telegram_user_id=100,
            telegram_username="swettka",
            text="+1 | деф | Swettka | Первая волна",
            message_date=timezone.now(),
            message_thread_id=12,
            status=TelegramMessage.Status.PROCESSED,
        )

    def _login(self, user):
        self.client.login(username=user, password="test-password-123")

    def _post_json(self, url, payload):
        return self.client.post(
            url,
            data=payload,
            content_type="application/json",
        )

    # ---------- Доступ ----------

    def test_page_anonymous_redirects_to_login(self):
        response = self.client.get(reverse("telegram_messages"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_page_member_returns_404(self):
        self._login("member")
        response = self.client.get(reverse("telegram_messages"))
        self.assertEqual(response.status_code, 404)

    def test_api_anonymous_returns_403_json(self):
        for url_name in ["send_reply", "send_message"]:
            response = self._post_json(reverse(url_name), {"text": "x"})
            self.assertEqual(response.status_code, 403, url_name)
            self.assertIn("application/json", response["Content-Type"])

    def test_api_member_returns_403_json(self):
        self._login("member")
        for url_name in ["send_reply", "send_message"]:
            response = self._post_json(reverse(url_name), {"text": "x"})
            self.assertEqual(response.status_code, 403, url_name)
            self.assertIn("application/json", response["Content-Type"])

    # ---------- Страница: табы и данные ----------

    def test_page_shows_tabs_and_counts(self):
        self._login("kl")
        response = self.client.get(reverse("telegram_messages"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Входящие (1)", content)
        self.assertIn("Исходящие (0)", content)
        self.assertIn("Все (1)", content)

    def test_default_tab_is_incoming(self):
        self._login("kl")
        response = self.client.get(reverse("telegram_messages"))
        self.assertEqual(response.context["tab"], "incoming")

    def test_tab_param_all(self):
        self._login("kl")
        response = self.client.get(reverse("telegram_messages"), {"tab": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["tab"], "all")

    def test_incoming_and_outgoing_pagination_20(self):
        self._login("kl")
        # 25 incoming
        for i in range(25):
            TelegramMessage.objects.create(
                telegram_chat_id=10,
                telegram_message_id=1000 + i,
                text=f"+1 | деф | Swettka | msg {i}",
                message_date=timezone.now(),
                status=TelegramMessage.Status.PROCESSED,
            )
        # 25 outgoing
        for i in range(25):
            OutgoingMessage.objects.create(
                telegram_chat_id=_GROUP_CHAT_ID,
                telegram_message_id=2000 + i,
                text=f"out {i}",
                sent_by=self.staff,
            )

        response = self.client.get(reverse("telegram_messages"))
        self.assertEqual(response.status_code, 200)
        # Входящие — 26 всего (1 + 25) => 2 страницы
        self.assertEqual(len(response.context["incoming_page"].object_list), 20)
        self.assertEqual(response.context["incoming_page"].paginator.num_pages, 2)
        # Исходящие — 25 => 2 страницы
        self.assertEqual(len(response.context["outgoing_page"].object_list), 20)
        self.assertEqual(response.context["outgoing_page"].paginator.num_pages, 2)

    def test_all_tab_merges_and_paginates(self):
        self._login("kl")
        for i in range(25):
            OutgoingMessage.objects.create(
                telegram_chat_id=_GROUP_CHAT_ID,
                telegram_message_id=3000 + i,
                text=f"out {i}",
                sent_by=self.staff,
            )
        response = self.client.get(reverse("telegram_messages"), {"tab": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["all_page"].object_list), 20)
        self.assertEqual(response.context["all_page"].paginator.num_pages, 2)

    def test_outgoing_table_shows_topic_and_sender(self):
        self._login("kl")
        OutgoingMessage.objects.create(
            telegram_chat_id=_GROUP_CHAT_ID,
            telegram_message_id=4000,
            text="сообщение в тему",
            sent_by=self.staff,
            topic_name="FORTS",
            reply_to_text="исходный текст",
        )
        response = self.client.get(reverse("telegram_messages"), {"tab": "outgoing"})
        content = response.content.decode()
        self.assertIn("сообщение в тему", content)
        self.assertIn("FORTS", content)
        self.assertIn("исходный текст", content)
        self.assertIn(self.staff.username, content)

    # ---------- Активная группа ----------

    def test_only_one_active_group_constraint(self):
        """БД запрещает существование более одной активной группы."""
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TelegramSettings.objects.create(
                    name="Вторая группа",
                    group_chat_id=-1009998887777,
                    is_active=True,
                )
        self.assertEqual(TelegramSettings.objects.filter(is_active=True).count(), 1)

    def test_telegram_topics_show_active_group_only(self):
        """В select попадают темы только активной группы."""
        self._login("kl")
        inactive = TelegramSettings.objects.create(
            name="Неактивная группа",
            group_chat_id=-1005556667777,
            is_active=False,
        )
        TelegramTopic.objects.create(
            name="SECRET", thread_id=99, is_active=True, group=inactive
        )
        response = self.client.get(reverse("telegram_messages"))
        context_topics = response.context["telegram_topics"]
        names = {t.name for t in context_topics}
        self.assertIn("FORTS", names)
        self.assertIn("FARM", names)
        self.assertNotIn("SECRET", names)

    def test_no_active_group_yields_empty_topics(self):
        """Без активной группы список тем пуст."""
        self._login("kl")
        self.group.is_active = False
        self.group.save(update_fields=["is_active"])
        response = self.client.get(reverse("telegram_messages"))
        self.assertEqual(list(response.context["telegram_topics"]), [])

    def test_active_group_without_topics_yields_empty(self):
        """Активная группа есть, но тем нет — список пуст."""
        self._login("kl")
        # Удаляем темы из активной группы
        TelegramTopic.objects.filter(group=self.group).delete()
        response = self.client.get(reverse("telegram_messages"))
        self.assertEqual(list(response.context["telegram_topics"]), [])

    def test_send_new_message_uses_active_group(self):
        """Отправка нового сообщения уходит в активную группу, а не в неактивную."""
        self._login("kl")
        inactive = TelegramSettings.objects.create(
            name="Неактивная группа",
            group_chat_id=-1005556667777,
            is_active=False,
        )
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 888},
            }
            self._post_json(
                reverse("send_message"),
                {"text": "В активную группу", "thread_id": ""},
            )

        _, kwargs = bot_instance.send_message.call_args
        self.assertEqual(kwargs["chat_id"], _GROUP_CHAT_ID)
        om = OutgoingMessage.objects.get()
        self.assertEqual(om.telegram_chat_id, _GROUP_CHAT_ID)

    # ---------- Отправка reply ----------

    def test_send_reply_success(self):
        self._login("kl")
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 555},
            }
            response = self._post_json(
                reverse("send_reply"),
                {"telegram_message_id": self.incoming.pk, "text": "Ответ КЛ"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["message_id"], 555)

        # OutgoingMessage записан в аудит с корректными данными
        om = OutgoingMessage.objects.get()
        self.assertEqual(om.status, OutgoingMessage.Status.SENT)
        self.assertEqual(om.telegram_chat_id, 10)
        self.assertEqual(om.telegram_message_id, 555)
        self.assertEqual(om.text, "Ответ КЛ")
        self.assertEqual(om.reply_to_message_id, 20)
        self.assertEqual(om.reply_to_text, "+1 | деф | Swettka | Первая волна")
        self.assertEqual(om.topic_name, "FORTS")  # по thread_id 12
        self.assertEqual(om.sent_by, self.staff)

        # в тему передан thread_id для надёжности
        _, kwargs = bot_instance.send_message.call_args
        self.assertEqual(kwargs["chat_id"], 10)
        self.assertEqual(kwargs["reply_to_message_id"], 20)
        self.assertEqual(kwargs["message_thread_id"], 12)

    def test_send_reply_error_creates_error_audit(self):
        self._login("kl")
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.side_effect = TelegramAPIError("boom")
            response = self._post_json(
                reverse("send_reply"),
                {"telegram_message_id": self.incoming.pk, "text": "текст"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

        om = OutgoingMessage.objects.get()
        self.assertEqual(om.status, OutgoingMessage.Status.ERROR)
        self.assertIn("boom", om.error_text)
        self.assertEqual(om.reply_to_text, "+1 | деф | Swettka | Первая волна")

    def test_send_reply_empty_text_rejected(self):
        self._login("kl")
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            response = self._post_json(
                reverse("send_reply"),
                {"telegram_message_id": self.incoming.pk, "text": "   "},
            )
            BotMock.return_value.send_message.assert_not_called()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(OutgoingMessage.objects.count(), 0)

    def test_send_reply_truncates_long_text(self):
        self._login("kl")
        long_text = "а" * 5000
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 777},
            }
            response = self._post_json(
                reverse("send_reply"),
                {"telegram_message_id": self.incoming.pk, "text": long_text},
            )

        self.assertEqual(response.status_code, 200)
        _, kwargs = bot_instance.send_message.call_args
        self.assertEqual(len(kwargs["text"]), 4096)
        om = OutgoingMessage.objects.get()
        self.assertEqual(len(om.text), 4096)

    # ---------- PENDING-паттерн ----------

    def test_send_reply_creates_pending_record_before_telegram_call(self):
        """Аудит-запись (PENDING) существует ещё до вызова Telegram API,
        затем становится SENT с реальным message_id."""
        self._login("kl")
        seen = {}

        def fake_send_message(*args, **kwargs):
            seen["pending_exists"] = OutgoingMessage.objects.filter(
                status=OutgoingMessage.Status.PENDING
            ).exists()
            return {"ok": True, "result": {"message_id": 555}}

        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            BotMock.return_value.send_message.side_effect = fake_send_message
            response = self._post_json(
                reverse("send_reply"),
                {"telegram_message_id": self.incoming.pk, "text": "Ответ"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(seen["pending_exists"])
        om = OutgoingMessage.objects.get()
        self.assertEqual(om.status, OutgoingMessage.Status.SENT)
        self.assertEqual(om.telegram_message_id, 555)

    def test_send_reply_record_survives_finalize_failure_as_pending(self):
        """Если финализация (обновление после успешной отправки) падает,
        аудит-запись не теряется и остаётся в PENDING."""
        self._login("kl")
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 555},
            }
            with mock.patch(
                "core.services.messaging_service._update_outgoing",
                side_effect=RuntimeError("finalize boom"),
            ):
                response = self._post_json(
                    reverse("send_reply"),
                    {"telegram_message_id": self.incoming.pk, "text": "Ответ"},
                )

        self.assertEqual(response.status_code, 500)
        om = OutgoingMessage.objects.get()
        self.assertEqual(om.status, OutgoingMessage.Status.PENDING)
        self.assertEqual(om.text, "Ответ")
        self.assertEqual(om.reply_to_message_id, 20)

    # ---------- Отправка нового сообщения ----------

    def test_send_new_message_to_topic(self):
        self._login("kl")
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 888},
            }
            response = self._post_json(
                reverse("send_message"),
                {"text": "Привет всем", "thread_id": "13"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        _, kwargs = bot_instance.send_message.call_args
        self.assertEqual(kwargs["chat_id"], _GROUP_CHAT_ID)
        self.assertEqual(kwargs["message_thread_id"], 13)

        om = OutgoingMessage.objects.get()
        self.assertEqual(om.status, OutgoingMessage.Status.SENT)
        self.assertEqual(om.telegram_chat_id, _GROUP_CHAT_ID)
        self.assertEqual(om.topic_name, "FARM")
        self.assertEqual(om.text, "Привет всем")

    def test_send_new_message_to_general_flow(self):
        self._login("kl")
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 999},
            }
            response = self._post_json(
                reverse("send_message"),
                {"text": "Общее сообщение", "thread_id": ""},
            )

        self.assertEqual(response.status_code, 200)
        _, kwargs = bot_instance.send_message.call_args
        self.assertEqual(kwargs["chat_id"], _GROUP_CHAT_ID)
        self.assertIsNone(kwargs["message_thread_id"])

        om = OutgoingMessage.objects.get()
        self.assertEqual(om.topic_name, "")
        self.assertEqual(om.status, OutgoingMessage.Status.SENT)

    def test_send_new_message_without_group_settings_errors(self):
        self._login("kl")
        TelegramSettings.objects.all().delete()
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            response = self._post_json(
                reverse("send_message"),
                {"text": "текст", "thread_id": ""},
            )
            BotMock.return_value.send_message.assert_not_called()

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("Группы", data["error"])
        self.assertEqual(OutgoingMessage.objects.count(), 0)

    def test_send_new_message_error_creates_error_audit(self):
        self._login("kl")
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.side_effect = TelegramAPIError("api down")
            response = self._post_json(
                reverse("send_message"),
                {"text": "текст", "thread_id": ""},
            )

        self.assertEqual(response.status_code, 400)
        om = OutgoingMessage.objects.get()
        self.assertEqual(om.status, OutgoingMessage.Status.ERROR)
        self.assertIn("api down", om.error_text)

    # ---------- CSRF ----------

    def test_post_without_csrf_token_returns_403(self):
        """Django CSRF rejects POST without a token (returns 403)."""
        self._login("kl")
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        response = csrf_client.post(
            reverse("send_reply"),
            data={"telegram_message_id": self.incoming.pk, "text": "x"},
        )
        self.assertEqual(response.status_code, 403)

    # ---------- Аудит: тема и исходный текст ----------

    def test_reply_audit_stores_thread_topic_and_original_text(self):
        self._login("kl")
        tm = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=999,
            text="+0,5 | фарм | Swettka | реп",
            message_date=timezone.now(),
            message_thread_id=13,
            status=TelegramMessage.Status.PROCESSED,
        )
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 111},
            }
            self._post_json(
                reverse("send_reply"),
                {"telegram_message_id": tm.pk, "text": "Ок"},
            )

        om = OutgoingMessage.objects.get()
        self.assertEqual(om.reply_to_text, "+0,5 | фарм | Swettka | реп")
        self.assertEqual(om.topic_name, "FARM")
        self.assertEqual(om.reply_to_message_id, 999)
