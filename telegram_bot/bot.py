"""Synchronous Telegram Bot API client based on requests."""
from typing import List, Optional

import requests
from django.conf import settings

_GET_UPDATES_URL = "https://api.telegram.org/bot{token}/getUpdates"


class TelegramAPIError(RuntimeError):
    """Raised when a Telegram Bot API call fails.

    The string representation NEVER contains the bot token.
    """


class TelegramBot:
    """Minimal long-polling client for the Telegram Bot API."""

    def __init__(self, token: Optional[str] = None):
        self.token = token if token is not None else settings.TELEGRAM_BOT_TOKEN
        self._get_updates_url = _GET_UPDATES_URL.format(token=self.token)

    def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> List[dict]:
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        try:
            response = requests.get(
                self._get_updates_url,
                params=params,
                timeout=timeout + 10,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TelegramAPIError(
                f"Telegram getUpdates failed: {type(exc).__name__}"
            ) from exc
        data = response.json()
        if not data.get("ok"):
            raise TelegramAPIError(
                f"Telegram API error in getUpdates: {data.get('description', 'unknown')}"
            )
        return data.get("result", [])

    def send_message(self, chat_id: int, text: str) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            response = requests.post(
                url,
                data={"chat_id": chat_id, "text": text},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TelegramAPIError(
                f"Telegram sendMessage failed: {type(exc).__name__}"
            ) from exc
        data = response.json()
        if not data.get("ok"):
            raise TelegramAPIError(
                f"Telegram API error in sendMessage: {data.get('description', 'unknown')}"
            )
        return data