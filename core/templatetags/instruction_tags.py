"""Template filter rendering instruction content (lightweight mini-markup).

Parses plain text with a small deterministic markup (headings, code blocks,
lists, dividers, note callouts, inline bold/code) into safe HTML.
No external dependencies, no models/migrations involved.

Security: every piece of user content is escaped with ``html.escape`` before
any structural/inline tag is inserted. Structural tags are produced only by
this parser; ``mark_safe`` is never applied to raw user data.
"""
import html
import re

from django import template
from django.utils.safestring import mark_safe, SafeString

register = template.Library()

_DIVIDER_RE = re.compile(r"[-\u2014]{3,}")
_OL_ITEM_RE = re.compile(r"^(\d+)[.)]\s*(.*)$")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _escape(text: str) -> str:
    """Escape user text for safe insertion into HTML output."""
    return html.escape(text)


def _apply_inline(text: str) -> str:
    """Apply inline markup on an already-escaped fragment.

    ``...`` first protects any ``**`` inside a code span from being turned
    into bold.
    """
    text = _INLINE_CODE_RE.sub(
        r'<code class="instruction-highlight">\1</code>', text
    )
    text = _INLINE_BOLD_RE.sub(r"<strong>\1</strong>", text)
    return text


def render_instruction_html(content: str) -> str:
    """Render plain-text instruction content into safe HTML."""
    if not content or not content.strip():
        return ""
    return "\n".join(_render_lines(content.splitlines()))


def _render_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    index = 0
    count = len(lines)
    while index < count:
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        if line.startswith("## "):
            out.append(
                f'<h2 class="instruction-subheading">'
                f'{_apply_inline(_escape(line[3:].strip()))}</h2>'
            )
            index += 1
            continue

        if _DIVIDER_RE.fullmatch(line):
            out.append('<hr class="instruction-divider">')
            index += 1
            continue

        if line.startswith(">"):
            block: list[str] = []
            while index < count:
                item = lines[index].strip()
                if item.startswith(">"):
                    block.append(_apply_inline(_escape(item[1:].strip())))
                    index += 1
                else:
                    break
            out.append(
                f'<pre class="instruction-code-block"><code>'
                f'{"\n".join(block)}</code></pre>'
            )
            continue

        note_class = _note_class(line)
        if note_class is not None:
            text = _apply_inline(_escape(line[2:].strip()))
            css = f" {note_class}" if note_class else ""
            out.append(f'<div class="instruction-note{css}">{text}</div>')
            index += 1
            continue

        if _OL_ITEM_RE.match(line):
            items: list[str] = []
            while index < count:
                item = lines[index].strip()
                match = _OL_ITEM_RE.match(item)
                if match is None:
                    break
                items.append(f"<li>{_apply_inline(_escape(match.group(2).strip()))}</li>")
                index += 1
            out.append(f'<ol class="instruction-fields">{"".join(items)}</ol>')
            continue

        if line.startswith("- "):
            items: list[str] = []
            while index < count:
                item = lines[index].strip()
                if item.startswith("- "):
                    items.append(f"<li>{_apply_inline(_escape(item[2:].strip()))}</li>")
                    index += 1
                else:
                    break
            out.append(f'<ul class="instruction-list">{"".join(items)}</ul>')
            continue

        out.append(f"<p>{_apply_inline(_escape(line))}</p>")
        index += 1
    return out


def _note_class(line: str) -> str | None:
    """Return the CSS modifier for a callout line, or None if not a callout."""
    if line.startswith("💡 "):
        return ""
    if line.startswith("⚠ "):
        return "warning"
    if line.startswith("❗ "):
        return "critical"
    return None


@register.filter(name="render_instruction")
def render_instruction(value) -> SafeString:
    """Template filter: render instruction content as safe HTML."""
    return mark_safe(render_instruction_html(value or ""))
