"""Tests for favicon / brand markup in the base template."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class BrandingMarkupTests(TestCase):
    """Base template: favicon links and brand logo marker presence."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.client.login(username="kl", password="test-password-123")

    def test_favicon_links_present_in_head(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("core/images/favicon.ico", content)
        self.assertIn("core/images/icon-192.png", content)
        self.assertIn("core/images/apple-touch-icon.png", content)
        self.assertIn('rel="icon"', content)
        self.assertIn('rel="apple-touch-icon"', content)

    def test_brand_link_present_with_aria_label_and_href(self):
        response = self.client.get(reverse("dashboard"))
        content = response.content.decode()
        self.assertIn('class="brand"', content)
        self.assertIn('aria-label="Smartline"', content)
        self.assertIn('href="%s"' % reverse("dashboard"), content)

    def test_brand_name_span_with_word_smartline(self):
        """The brand link contains a <span class="brand-name">Smartline</span>."""
        response = self.client.get(reverse("dashboard"))
        content = response.content.decode()
        brand_start = content.index('class="brand"')
        brand_end = content.index("</a>", brand_start)
        brand_block = content[brand_start:brand_end]
        self.assertIn('<span class="brand-name">Smartline</span>', brand_block)

    def test_brand_name_span_text_is_smartline(self):
        """The span.brand-name contains exactly 'Smartline'."""
        response = self.client.get(reverse("dashboard"))
        content = response.content.decode()
        self.assertIn(">Smartline<", content)


class LoginPageNavTests(TestCase):
    """Login page shows brand only, hiding navigation and logout button."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )

    def test_login_page_shows_brand_but_no_navigation(self):
        """
        Anonymous user on the login page sees only the brand in the header,
        no navigation links and no logout button.
        """
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # The header region contains only the brand.
        header_start = content.index("<header>")
        header_end = content.index("</header>")
        header = content[header_start:header_end]
        self.assertIn('class="brand"', header)
        self.assertIn("Smartline", header)
        # No navbar nav or auth links in header.
        self.assertNotIn("Дашборд", header)
        self.assertNotIn("Выйти", header)
        # The login card's own "Зарегистрироваться" link is in <main>, not <header>.

    def test_dashboard_still_shows_navigation_after_login(self):
        """Navigation remains visible on non-login pages."""
        self.client.login(username="kl", password="test-password-123")
        response = self.client.get(reverse("dashboard"))
        content = response.content.decode()
        header_start = content.index("<header>")
        header_end = content.index("</header>")
        header = content[header_start:header_end]
        self.assertIn("Дашборд", header)
        self.assertIn("Выйти", header)
