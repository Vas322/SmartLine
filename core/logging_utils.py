"""Centralized redaction of secrets in logs.

Guarantees that secrets (Telegram bot token, Django secret key, DB password)
never appear in log output, regardless of where they originate.
"""
import logging
from typing import List

REDACTED = "***"
_secrets_cache: List[str] = []


def collect_secrets() -> List[str]:
    global _secrets_cache
    if not _secrets_cache:
        try:
            from django.conf import settings
        except Exception:
            return _secrets_cache
        candidates: List[str] = []
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if token:
            candidates.append(token)
        key = getattr(settings, "SECRET_KEY", "")
        if key:
            candidates.append(key)
        try:
            pwd = settings.DATABASES["default"]["PASSWORD"]
            if pwd:
                candidates.append(pwd)
        except Exception:
            pass
        seen = set()
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                _secrets_cache.append(candidate)
    return _secrets_cache


def redact(text: str) -> str:
    if not text:
        return text
    for secret in collect_secrets():
        if secret and secret in text:
            text = text.replace(secret, REDACTED)
    return text


class RedactingFilter(logging.Filter):
    """Redact secrets from record.msg and record.args (pre-format layer)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = self._redact_args(record.args)
        return True

    @staticmethod
    def _redact_args(args):
        if isinstance(args, dict):
            return {k: (redact(v) if isinstance(v, str) else v) for k, v in args.items()}
        if isinstance(args, (tuple, list)):
            return tuple(redact(a) if isinstance(a, str) else a for a in args)
        return args


class RedactingFormatter(logging.Formatter):
    """Redact secrets from the final formatted output, including exc_text."""

    def format(self, record: logging.LogRecord) -> str:
        output = super().format(record)
        return redact(output)
