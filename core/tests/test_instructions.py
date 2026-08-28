"""Tests for the instructions web interface."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import Instruction

User = get_user_model()


def _create_member_user():
    """Create a user in the Members group."""
    user = User.objects.create_user("member", password="p")
    members_group, _ = Group.objects.get_or_create(name="Members")
    user.groups.add(members_group)
    return user


def _create_staff_user():
    """Create a staff user."""
    return User.objects.create_user("staff", password="p", is_staff=True)


class InstructionsAccessTests(TestCase):
    def test_anonymous_redirected(self):
        response = self.client.get(reverse("instructions"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_anonymous_edit_redirected(self):
        instr = Instruction.objects.create(slug="x", title="X", content="c")
        response = self.client.post(
            reverse("instruction_edit", args=[instr.pk]),
            {"slug": "x", "title": "Y", "content": "d"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_list_shows_seeded_instruction(self):
        self.client.force_login(_create_member_user())
        response = self.client.get(reverse("instructions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Запись активности на форте")

    def test_edit_updates_content_and_author(self):
        instr = Instruction.objects.create(slug="x", title="X", content="c")
        user = _create_staff_user()
        self.client.force_login(user)
        response = self.client.post(
            reverse("instruction_edit", args=[instr.pk]),
            {"slug": "x", "title": "New", "content": "new content"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=1", response["Location"])
        instr.refresh_from_db()
        self.assertEqual(instr.content, "new content")
        self.assertEqual(instr.title, "New")
        self.assertEqual(instr.updated_by, user)
        self.assertIsNotNone(instr.updated_at)

    def test_saved_marker_present(self):
        Instruction.objects.create(slug="x", title="X", content="c")
        self.client.force_login(_create_member_user())
        response = self.client.get(reverse("instructions") + "?saved=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="edit-notify"')


class InstructionWebTests(TestCase):
    def _login(self):
        self.client.force_login(_create_member_user())

    def test_detail_page_renders_content(self):
        instr = Instruction.objects.create(slug="d1", title="DT", content="Detail body")
        self._login()
        response = self.client.get(reverse("instruction_detail", args=[instr.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail body")
        self.assertContains(response, "DT")
        # instruction_edit link only visible to staff
        self.assertNotContains(response, reverse("instruction_edit", args=[instr.pk]))

    def test_detail_page_404_unknown_pk(self):
        self._login()
        response = self.client.get(reverse("instruction_detail", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_list_title_links_to_detail(self):
        instr = Instruction.objects.create(slug="d2", title="LT", content="LC")
        self._login()
        response = self.client.get(reverse("instructions"))
        self.assertContains(response, reverse("instruction_detail", args=[instr.pk]))
