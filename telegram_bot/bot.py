"""Synchronous Telegram Bot API client based on requests."""
from typing import List, Optional

import requests
from django.conf import settings

_GET_UPDATES_URL = "https://api.telegram.org/bot{token}/getUpdates"


class TelegramBot:
    """Minimal long-polling client for the Telegram Bot API."""

    def __init__(self, token: Optional[str] = None):
        self.token = token if token is not None else settings.TELEGRAM_BOT_TOKEN
        self._get_updates_url = _GET_UPDATES_URL.format(token=self.token)

    def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> List[dict]:
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = requests.get(
            self._get_updates_url,
            params=params,
            timeout=timeout + 10,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API returned an error: {data}")
        return data.get("result", [])

    def send_message(self, chat_id: int, text: str) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        response = requests.post(
            url,
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API returned an error: {data}")
        return data