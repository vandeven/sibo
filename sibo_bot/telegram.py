import logging

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"

LOCATION_KEYBOARD = {
    "keyboard": [[{"text": "📍 Share my location", "request_location": True}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}


class TelegramClient:
    """Thin async wrapper over the Telegram Bot API. Messages use HTML parse mode, so escape user text."""

    def __init__(self, token: str, http: httpx.AsyncClient | None = None):
        self._token = token
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(10.0, write=60.0, read=60.0))

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _post(self, method: str, **kwargs) -> bool:
        if not self._token:
            logger.error("TELEGRAM_BOT_TOKEN is not configured; dropping %s.", method)
            return False
        try:
            response = await self._http.post(f"{API_BASE}/bot{self._token}/{method}", **kwargs)
        except httpx.HTTPError as e:
            logger.error("Telegram %s failed: %s", method, e)
            return False
        if response.status_code != 200:
            logger.error("Telegram %s returned %s: %s", method, response.status_code, response.text)
            return False
        return True

    async def send_message(self, chat_id: int, html_text: str, reply_markup: dict | None = None) -> bool:
        payload: dict = {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._post("sendMessage", json=payload)

    async def send_document(self, chat_id: int, content: bytes, filename: str, caption: str | None = None) -> bool:
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
        files = {"document": (filename, content, "application/pdf")}
        return await self._post("sendDocument", data=data, files=files)
