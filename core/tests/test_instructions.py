"""Tests for the instructions web interface."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Instruction

User = get_user_model()


class InstructionsAccessTests(TestCase):
    def test_anonymous_redirected(self):
        response = self.client.get(reverse("instructions"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_anonymous_edit_redirected(self):
        instr = Instruction.objects.create(slug="x", title="X", content="c")
        response = self.client.post(
            reverse("instructions"),
            {"pk": instr.pk, "title": "Y", "content": "d"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_list_shows_seeded_instruction(self):
        self.client.force_login(User.objects.create_user("kl", password="p"))
        response = self.client.get(reverse("instructions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Запись активности на форте")

    def test_edit_updates_content_and_author(self):
        instr = Instruction.objects.create(slug="x", title="X", content="c")
        user = User.objects.create_user("kl", password="p")
        self.client.force_login(user)
        response = self.client.post(
            reverse("instructions"),
            {"pk": instr.pk, "title": "New", "content": "new content"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=1", response["Location"])
        instr.refresh_from_db()
        self.assertEqual(instr.content, "new content")
        self.assertEqual(instr.title, "New")
        self.assertEqual(instr.updated_by, user)
        self.assertIsNotNone(instr.updated_at)

    def test_slug_not_changed_on_edit(self):
        instr = Instruction.objects.create(slug="keep-slug", title="X", content="c")
        user = User.objects.create_user("kl", password="p")
        self.client.force_login(user)
        self.client.post(
            reverse("instructions"),
            {"pk": instr.pk, "title": "New", "content": "c2", "slug": "hacked"},
        )
        instr.refresh_from_db()
        self.assertEqual(instr.slug, "keep-slug")

    def test_saved_marker_present(self):
        Instruction.objects.create(slug="x", title="X", content="c")
        self.client.force_login(User.objects.create_user("kl", password="p"))
        response = self.client.get(reverse("instructions") + "?saved=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="edit-notify"')

    def test_html_is_escaped(self):
        Instruction.objects.create(
            slug="x", title="X", content="<script>alert(1)</script>"
        )
        self.client.force_login(User.objects.create_user("kl", password="p"))
        response = self.client.get(reverse("instructions"))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_seeded_instruction_has_no_invalid_space_only_example(self):
        self.client.force_login(User.objects.create_user("kl", password="p"))
        response = self.client.get(reverse("instructions"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "+1 ДЕФ Swettka описание")
        self.assertContains(response, "+1 - ДЕФ - Swettka - описание")

    def test_instruction_explains_multinick(self):
        self.client.force_login(User.objects.create_user("kl", password="p"))
        response = self.client.get(reverse("instructions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Мульти-ник")
        self.assertContains(response, "Swettka, Vas, Dimas, Pocomaxa")
        self.assertContains(response, "0,5 | фарм | Ostin, Pocomaxa")