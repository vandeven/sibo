import hmac
import logging
import platform
from contextlib import asynccontextmanager
from html import escape

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, status

from sibo_bot.config import settings
from sibo_bot.models import SearchQuery
from sibo_bot.pdf import render_report, report_filename
from sibo_bot.rate_limit import Cooldown
from sibo_bot.research import ResearchError, RestaurantResearcher
from sibo_bot.telegram import TelegramClient
from sibo_bot.updates import MessageRouter, Reply, parse_update
from sibo_bot.version import APP_VERSION, get_commit_sha

logger = logging.getLogger(__name__)


class SearchService:
    """Runs one search end to end: confirmation -> Claude research -> PDF -> Telegram document."""

    def __init__(self, researcher: RestaurantResearcher, telegram: TelegramClient):
        self.researcher = researcher
        self.telegram = telegram

    async def run(self, chat_id: int, query: SearchQuery) -> None:
        cuisine = f" serving <b>{escape(query.cuisine)}</b>" if query.cuisine else ""
        await self.telegram.send_message(
            chat_id,
            f"🔍 Researching SIBO-friendly restaurants{cuisine} near <b>{escape(query.label)}</b>...\n"
            "This usually takes a few minutes. Your PDF report will follow. 📄",
        )
        try:
            report = await self.researcher.research(query)
            pdf_bytes = render_report(report)
        except ResearchError as e:
            await self.telegram.send_message(chat_id, f"❌ {escape(e.user_message)}")
            return
        except Exception:
            logger.exception("Search failed for chat %s (%s)", chat_id, query)
            await self.telegram.send_message(chat_id, "❌ Something went wrong while building your report. Please try again.")
            return

        caption = f"SIBO restaurant guide: {report.location_label}" + (f" ({report.cuisine})" if report.cuisine else "")
        if not await self.telegram.send_document(chat_id, pdf_bytes, report_filename(report), caption=caption):
            await self.telegram.send_message(chat_id, "⚠️ Sorry, I couldn't send your PDF report. Please try again later.")


def create_app(
    researcher: RestaurantResearcher | None = None,
    telegram: TelegramClient | None = None,
    cooldown: Cooldown | None = None,
) -> FastAPI:
    telegram = telegram or TelegramClient(settings.telegram_bot_token)
    search = SearchService(researcher or RestaurantResearcher(), telegram)
    cooldown = cooldown or Cooldown(settings.rate_limit_seconds)
    router = MessageRouter()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await telegram.aclose()

    app = FastAPI(
        title="SIBO Telegram Bot",
        version=APP_VERSION,
        description="Telegram webhook bot that researches SIBO-friendly restaurants with Claude and replies with a PDF.",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health():
        return {
            "status": "healthy",
            "version": APP_VERSION,
            "commit": get_commit_sha(),
            "python_version": platform.python_version(),
            "deployment": "google-cloud-run-buildpacks",
        }

    @app.post("/telegram/webhook")
    async def telegram_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        secret_token: str | None = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
    ):
        expected = settings.telegram_webhook_secret
        if expected and not hmac.compare_digest((secret_token or "").encode(), expected.encode()):
            logger.warning("Rejected webhook call with an invalid secret token.")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Telegram Bot API secret token header.")

        msg = parse_update(await request.json())
        if msg is None:
            return {"status": "ok"}

        allowed = settings.allowed_user_ids
        if allowed and msg.user_id not in allowed:
            logger.warning("Rejected message from non-whitelisted user %s", msg.user_id)
            await telegram.send_message(msg.chat_id, "⛔ Access denied: you are not authorized to use this bot.")
            return {"status": "ok"}

        action = router.route(msg)
        if isinstance(action, Reply):
            await telegram.send_message(msg.chat_id, action.html, action.reply_markup)
            return {"status": "ok"}

        wait = cooldown.try_acquire(msg.user_id or msg.chat_id)
        if wait:
            await telegram.send_message(msg.chat_id, f"⏳ Please wait {wait:.0f} more seconds before starting a new search.")
            return {"status": "ok"}

        background_tasks.add_task(search.run, msg.chat_id, action)
        return {"status": "ok"}

    return app
