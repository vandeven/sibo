"""Turns Telegram updates into either a reply or a search query."""

import time
from dataclasses import dataclass
from html import escape

from pydantic import ValidationError

from sibo_bot.models import SearchQuery
from sibo_bot.telegram import LOCATION_KEYBOARD
from sibo_bot.version import APP_VERSION, get_commit_sha

PENDING_CUISINE_TTL_SECONDS = 10 * 60


@dataclass(frozen=True)
class IncomingMessage:
    chat_id: int
    user_id: int | None
    first_name: str
    text: str = ""
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class Reply:
    html: str
    reply_markup: dict | None = None


def parse_update(payload: dict) -> IncomingMessage | None:
    """Returns None for updates the bot ignores (no message, no chat, or neither text nor location)."""
    message = payload.get("message") or payload.get("edited_message")
    if not message:
        return None
    chat_id = (message.get("chat") or {}).get("id")
    sender = message.get("from") or {}
    text = (message.get("text") or "").strip()
    location = message.get("location") or {}
    if not chat_id or not (text or location):
        return None
    return IncomingMessage(
        chat_id=chat_id,
        user_id=sender.get("id"),
        first_name=sender.get("first_name") or "there",
        text=text,
        latitude=location.get("latitude"),
        longitude=location.get("longitude"),
    )


HELP_TEXT = (
    "ℹ️ <b>How to use me</b>\n"
    "• Send a <b>city</b> and an optional <b>cuisine</b>, e.g. <code>Amsterdam</code> or "
    "<code>Wageningen Italian</code>\n"
    "• Tap <b>📍 Share my location</b> to search restaurants near you\n"
    "• <code>/near sushi</code> then share your location to search a cuisine near you\n\n"
    "You'll get a PDF with the top 5 best-rated and top 5 cheapest restaurants, the SIBO-friendly "
    "dishes and what to ask the waiter.\n\n"
    "<b>Commands:</b> /start, /help, /near, /status, /version"
)


def version_reply() -> Reply:
    return Reply(f"🏷️ <b>Version:</b> {APP_VERSION}\n📌 <b>Commit:</b> <code>{escape(get_commit_sha())}</code>")


class MessageRouter:
    """Decides what to do with a message. Remembers `/near <cuisine>` per chat until the location arrives."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._pending_cuisine: dict[int, tuple[str | None, float]] = {}

    def route(self, msg: IncomingMessage) -> Reply | SearchQuery:
        if msg.latitude is not None and msg.longitude is not None:
            return SearchQuery(latitude=msg.latitude, longitude=msg.longitude, cuisine=self._pop_cuisine(msg.chat_id))
        if msg.text.lower() == "version":
            return version_reply()
        if msg.text.startswith("/"):
            return self._command(msg)
        try:
            return SearchQuery.from_text(msg.text)
        except ValidationError:
            return Reply(HELP_TEXT, LOCATION_KEYBOARD)

    def _command(self, msg: IncomingMessage) -> Reply:
        command, _, argument = msg.text.partition(" ")
        command = command.split("@", 1)[0].lower()  # "/start@MyBot" in group chats
        argument = argument.strip()

        if command == "/start":
            return Reply(f"Hello {escape(msg.first_name)}! 👋 I find SIBO-friendly restaurants.\n\n{HELP_TEXT}", LOCATION_KEYBOARD)
        if command == "/near":
            self._pending_cuisine[msg.chat_id] = (argument or None, self._clock())
            what = f"<b>{escape(argument)}</b> restaurants" if argument else "restaurants"
            return Reply(f"📍 Share your location and I'll find SIBO-friendly {what} near you.", LOCATION_KEYBOARD)
        if command == "/status":
            return Reply(f"✅ <b>Bot status:</b> healthy\n📌 <b>Commit:</b> <code>{escape(get_commit_sha())}</code>")
        if command == "/version":
            return version_reply()
        return Reply(HELP_TEXT, LOCATION_KEYBOARD)

    def _pop_cuisine(self, chat_id: int) -> str | None:
        cuisine, created = self._pending_cuisine.pop(chat_id, (None, 0.0))
        if self._clock() - created > PENDING_CUISINE_TTL_SECONDS:
            return None
        return cuisine
