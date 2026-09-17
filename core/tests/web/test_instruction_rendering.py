"""Tests for the instruction mini-markup renderer (render_instruction filter)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import Instruction
from core.templatetags.instruction_tags import render_instruction_html

User = get_user_model()


def _create_member_user():
    """Create a user in the Members group."""
    user = User.objects.create_user("member", password="p")
    members_group, _ = Group.objects.get_or_create(name="Members")
    user.groups.add(members_group)
    return user


class RenderInstructionHtmlTests(TestCase):
    """Unit tests for the markup parser / template filter."""

    def test_renders_heading(self):
        html = render_instruction_html("## Как считается оплата")
        self.assertIn(
            '<h2 class="instruction-subheading">Как считается оплата</h2>', html
        )

    def test_renders_code_block(self):
        html = render_instruction_html("> 00:01–08:00 — 100 кк за 1 час")
        self.assertIn(
            '<pre class="instruction-code-block"><code>'
            "00:01–08:00 — 100 кк за 1 час</code></pre>",
            html,
        )

    def test_renders_consecutive_code_lines_as_single_block(self):
        html = render_instruction_html(
            "> 00:01–08:00 — 100 кк\n> 08:01–16:00 — 75 кк"
        )
        self.assertEqual(html.count("<pre"), 1)
        self.assertIn("100 кк\n08:01–16:00 — 75 кк", html)

    def test_renders_ordered_list(self):
        html = render_instruction_html("1. Первый пункт")
        self.assertIn(
            '<ol class="instruction-fields"><li>Первый пункт</li></ol>', html
        )

    def test_renders_consecutive_ordered_items_as_single_ol(self):
        html = render_instruction_html("1. Один\n2. Два")
        self.assertEqual(html.count("<ol"), 1)
        self.assertIn("<li>Один</li>", html)
        self.assertIn("<li>Два</li>", html)

    def test_renders_unordered_list(self):
        html = render_instruction_html("- FARM — не оплачивается.")
        self.assertIn(
            '<ul class="instruction-list">'
            "<li>FARM — не оплачивается.</li></ul>",
            html,
        )

    def test_renders_consecutive_unordered_items_as_single_ul(self):
        html = render_instruction_html("- Один\n- Два")
        self.assertEqual(html.count("<ul"), 1)
        self.assertIn("<li>Один</li>", html)
        self.assertIn("<li>Два</li>", html)

    def test_renders_divider(self):
        html = render_instruction_html("---")
        self.assertIn('<hr class="instruction-divider">', html)

    def test_renders_note_callouts(self):
        html = render_instruction_html(
            "💡 Тарифы устанавливает КЛ.\n"
            "⚠ Скриншот обязателен.\n"
            "❗ Критично!"
        )
        self.assertIn(
            '<div class="instruction-note">Тарифы устанавливает КЛ.</div>', html
        )
        self.assertIn(
            '<div class="instruction-note warning">Скриншот обязателен.</div>',
            html,
        )
        self.assertIn(
            '<div class="instruction-note critical">Критично!</div>', html
        )

    def test_renders_inline_code(self):
        html = render_instruction_html("Формат `+1 | деф`")
        self.assertIn(
            'Формат <code class="instruction-highlight">+1 | деф</code>', html
        )

    def test_renders_inline_bold(self):
        html = render_instruction_html("— **50 кк**")
        self.assertIn("— <strong>50 кк</strong>", html)

    def test_plain_paragraph(self):
        html = render_instruction_html("Обычный текст")
        self.assertEqual(html, "<p>Обычный текст</p>")

    def test_escapes_html_in_paragraph(self):
        html = render_instruction_html("<script>alert(1)</script>")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_escapes_html_inside_inline_bold(self):
        html = render_instruction_html("**<b>x</b>**")
        self.assertNotIn("<b>x</b>", html)
        self.assertIn("<strong>&lt;b&gt;x&lt;/b&gt;</strong>", html)

    def test_empty_content_no_exception(self):
        self.assertEqual(render_instruction_html(""), "")
        self.assertEqual(render_instruction_html("   \n  "), "")
        self.assertEqual(render_instruction_html(None), "")


class InstructionDetailRenderTests(TestCase):
    """instruction_detail.html uses render_instruction and renders markup."""

    def setUp(self):
        self.client.force_login(_create_member_user())

    def test_detail_page_renders_heading_markup(self):
        instr = Instruction.objects.create(
            slug="rates",
            title="Расценки",
            content="## Как считается оплата\n\n- DEF — оплачивается.",
        )
        response = self.client.get(reverse("instruction_detail", args=[instr.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, '<h2 class="instruction-subheading">Как считается оплата</h2>'
        )
        self.assertContains(
            response, '<ul class="instruction-list"><li>DEF — оплачивается.</li></ul>'
        )

    def test_detail_page_escapes_content(self):
        instr = Instruction.objects.create(
            slug="xss", title="XSS", content="<script>alert(1)</script>"
        )
        response = self.client.get(reverse("instruction_detail", args=[instr.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")
