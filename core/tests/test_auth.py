"""Tests for email registration, activation, password reset, and access control."""
from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.core import mail


class SignUpTest(TestCase):
    """Tests for user registration."""

    def test_signup_page_status(self):
        response = self.client.get("/register/")
        self.assertEqual(response.status_code, 200)

    def test_signup_form_valid(self):
        response = self.client.post("/register/", {
            "email": "test@example.com",
            "username": "testuser",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/activation-sent/")
        user = User.objects.get(username="testuser")
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, "test@example.com")

    def test_signup_sends_activation_email(self):
        self.client.post("/register/", {
            "email": "test@example.com",
            "username": "testuser",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Подтверждение регистрации", mail.outbox[0].subject)

    def test_signup_duplicate_email(self):
        User.objects.create_user("existing", "test@example.com", "pass12345!")
        response = self.client.post("/register/", {
            "email": "test@example.com",
            "username": "newuser",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_signup_duplicate_username(self):
        User.objects.create_user("testuser", "other@example.com", "pass12345!")
        response = self.client.post("/register/", {
            "email": "new@example.com",
            "username": "testuser",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 200)

    def test_signup_password_mismatch(self):
        response = self.client.post("/register/", {
            "email": "test@example.com",
            "username": "testuser",
            "password": "StrongPass123!",
            "password_confirm": "DifferentPass!",
        })
        self.assertEqual(response.status_code, 200)

    def test_signup_short_username(self):
        response = self.client.post("/register/", {
            "email": "test@example.com",
            "username": "ab",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 200)

    def test_signup_redirects_authenticated(self):
        user = User.objects.create_user("logged", "logged@example.com", "pass12345!")
        self.client.login(username="logged", password="pass12345!")
        response = self.client.get("/register/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")


class ActivationTest(TestCase):
    """Tests for email activation."""

    def setUp(self):
        self.user = User.objects.create_user(
            "testuser", "test@example.com", "StrongPass123!", is_active=False
        )

    def _get_activation_url(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        return f"/activate/{uid}/{token}/"

    def test_activation_activates_user(self):
        url = self._get_activation_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_activation_adds_to_members_group(self):
        url = self._get_activation_url()
        self.client.get(url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.groups.filter(name="Members").exists())

    def test_activation_invalid_token(self):
        response = self.client.get("/activate/AAAA/invalid-token/")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_activation_missing_user(self):
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        uid = urlsafe_base64_encode(force_bytes(99999))
        token = "invalid"
        response = self.client.get(f"/activate/{uid}/{token}/")
        self.assertEqual(response.status_code, 200)


class AccessControlTest(TestCase):
    """Tests for member_required and staff_member_required decorators."""

    def setUp(self):
        self.anon = Client()
        self.member = Client()
        self.staff = Client()
        self.admin = Client()

        self.member_user = User.objects.create_user("member", "m@test.com", "pass12345!")
        members_group, _ = Group.objects.get_or_create(name="Members")
        self.member_user.groups.add(members_group)
        self.member.login(username="member", password="pass12345!")

        self.staff_user = User.objects.create_user("staff", "s@test.com", "pass12345!", is_staff=True)
        self.staff.login(username="staff", password="pass12345!")

        self.admin_user = User.objects.create_superuser("admin", "a@test.com", "pass12345!")
        self.admin.login(username="admin", password="pass12345!")

    def test_anon_redirected_from_protected_pages(self):
        for url in ["/", "/players/", "/activities/", "/instructions/"]:
            response = self.anon.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response.url)

    def test_member_can_access_dashboard(self):
        response = self.member.get("/")
        self.assertEqual(response.status_code, 200)

    def test_member_can_access_instructions(self):
        response = self.member.get("/instructions/")
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_access_players(self):
        response = self.member.get("/players/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/", response.url)

    def test_member_cannot_access_activities(self):
        response = self.member.get("/activities/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/", response.url)

    def test_member_cannot_access_settings(self):
        response = self.member.get("/settings/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/", response.url)

    def test_member_cannot_access_errors(self):
        response = self.member.get("/processing_errors/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/", response.url)

    def test_staff_can_access_all(self):
        for url in ["/", "/players/", "/activities/", "/instructions/", "/settings/",
                     "/processing_errors/", "/telegram-messages/"]:
            response = self.staff.get(url)
            self.assertEqual(response.status_code, 200, f"Staff denied access to {url}")

    def test_user_without_group_cannot_access_member_pages(self):
        user = User.objects.create_user("nogroup", "n@test.com", "pass12345!")
        self.member.login(username="nogroup", password="pass12345!")
        response = self.member.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


class ProfileTest(TestCase):
    """Tests for profile page."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", "test@example.com", "pass12345!")
        self.client.login(username="testuser", password="pass12345!")

    def test_profile_page_status(self):
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 200)

    def test_profile_shows_username(self):
        response = self.client.get("/profile/")
        self.assertContains(response, "testuser")

    def test_profile_shows_email(self):
        response = self.client.get("/profile/")
        self.assertContains(response, "test@example.com")

    def test_profile_requires_login(self):
        self.client.logout()
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


class LoginLinksTest(TestCase):
    """Tests for login page links."""

    def test_login_page_has_register_link(self):
        response = self.client.get("/login/")
        self.assertContains(response, "/register/")

    def test_login_page_has_password_reset_link(self):
        response = self.client.get("/login/")
        self.assertContains(response, "/password-reset/")