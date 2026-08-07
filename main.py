import os
import logging
from typing import Dict, Any, Tuple, Optional
from fastapi import FastAPI, Header, HTTPException, Request, BackgroundTasks, status

from config import settings
from gemini_service import research_sibo_restaurants
from pdf_generator import generate_sibo_pdf
from telegram_service import send_telegram_message, send_telegram_document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SIBO Telegram Bot & PDF Generator",
    version="1.0.0",
    description="Cloud Run webhook bot that researches SIBO restaurants using Gemini Search Grounding and delivers PDFs via Telegram."
)


def parse_city_and_meal_type(text: str) -> Tuple[str, Optional[str]]:
    """
    Parses incoming user text into city and optional meal type.
    Example: 'Wageningen Italian' -> ('Wageningen', 'Italian')
    Example: 'Amsterdam' -> ('Amsterdam', None)
    """
    text = text.strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def handle_user_command(text: str, user_name: str = "User") -> str:
    """
    Handles slash commands (/start, /help, /status).
    """
    cmd = text.strip().lower()
    if cmd.startswith("/start"):
        return (
            f"Hello {user_name}! 👋\n\n"
            "I am your SIBO-Friendly Restaurant Guide Bot.\n\n"
            "📌 *How to use me:*\n"
            "Send me a message with a **City** and an optional **Meal Type / Cuisine**.\n\n"
            "Examples:\n"
            "• `Amsterdam` (searches full menus across top restaurants)\n"
            "• `Wageningen Italian` (searches for Italian SIBO options)\n"
            "• `Rotterdam Sushi`\n\n"
            "Running on Python 3.14.7 | Google Cloud Run"
        )
    elif cmd.startswith("/help"):
        return (
            "ℹ️ *Available Commands:*\n"
            "• `/start` - Start bot and show usage guide\n"
            "• `/help` - Show help information\n"
            "• `/status` - Check bot status\n\n"
            "Or send any city name (e.g. `Utrecht` or `Groningen Lunch`) to generate a PDF guide!"
        )
    elif cmd.startswith("/status"):
        return "✅ Bot is Healthy & Running on Google Cloud Run!"
    else:
        return f"Echo test: {text}"


async def process_sibo_request_background(chat_id: int, city: str, meal_type: Optional[str]):
    """
    Background worker function that conducts Gemini search grounding research,
    renders the PDF report, and sends it back to Telegram.
    """
    try:
        # Step 1: Send initial confirmation message to Telegram
        meal_desc = f" for '{meal_type}'" if meal_type else ""
        confirm_msg = (
            f"🔍 *Researching SIBO-friendly restaurants in {city}{meal_desc}...*\n"
            "Compiling ratings, prices, and waiter modification instructions into your custom PDF report. "
            "Please wait a moment! 📄"
        )
        await send_telegram_message(chat_id, confirm_msg)

        # Step 2: Gemini Search Grounding
        data = research_sibo_restaurants(city, meal_type)

        # Step 3: PDF Generation
        pdf_path = generate_sibo_pdf(data)

        # Step 4: Telegram Document Delivery
        caption = f"📄 SIBO Restaurant Guide for {city}" + (f" ({meal_type})" if meal_type else "")
        success = await send_telegram_document(chat_id, pdf_path, caption=caption)

        # Step 5: Clean up temp file
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

        if not success:
            await send_telegram_message(
                chat_id,
                "⚠️ Sorry, there was an issue sending your PDF report. Please try again later."
            )

    except Exception as e:
        logger.error(f"Error processing SIBO request background job: {e}")
        await send_telegram_message(
            chat_id,
            f"❌ Error processing request for {city}: {str(e)}"
        )


@app.get("/health")
def health_check():
    """Health check endpoint for GCP Cloud Run container probing."""
    commit_sha = os.environ.get("COMMIT_SHA") or os.environ.get("K_REVISION") or ""
    if not commit_sha:
        try:
            import subprocess
            commit_sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        except Exception:
            commit_sha = "unknown"

    return {
        "status": "healthy",
        "version": "1.0.0",
        "commit": commit_sha,
        "python_version": "3.13.1",
        "deployment": "google-cloud-run-buildpacks"
    }


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token")
):
    """
    Telegram webhook endpoint. Validates secret header token and user ID whitelist.
    Responds HTTP 200 OK immediately and processes Gemini research in the background.
    """
    # 1. Header Secret Token Validation
    expected_secret = settings.telegram_webhook_secret
    if expected_secret:
        if x_telegram_bot_api_secret_token != expected_secret:
            logger.warning("Unauthorized webhook call: Invalid secret header token.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Telegram Bot API secret token header."
            )

    # 2. Parse Telegram Payload
    payload = await request.json()
    message = payload.get("message") or payload.get("edited_message")
    if not message:
        return {"status": "ok", "detail": "No message payload"}

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user = message.get("from", {})
    user_id = user.get("id")
    text = message.get("text", "").strip()

    if not chat_id or not text:
        return {"status": "ok"}

    # 3. User ID Whitelist Validation
    allowed_set = settings.allowed_user_ids_set
    if allowed_set and user_id not in allowed_set:
        logger.warning(f"Unauthorized user ID attempting access: {user_id}")
        # Optionally notify unauthorized user
        await send_telegram_message(chat_id, "⛔ Access denied: You are not authorized to use this bot.")
        return {"status": "ok", "detail": "User not in whitelist"}

    # 4. Handle Slash Commands or Process Search Query
    if text.startswith("/"):
        first_name = user.get("first_name", "User")
        reply_text = handle_user_command(text, first_name)
        await send_telegram_message(chat_id, reply_text)
        return {"status": "ok"}

    # 5. Extract City & Meal Type and Queue Background Job
    city, meal_type = parse_city_and_meal_type(text)
    background_tasks.add_task(process_sibo_request_background, chat_id, city, meal_type)

    return {"status": "ok"}
