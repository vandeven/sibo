import os
import logging
from typing import Optional
import httpx

from config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


async def send_telegram_message(chat_id: int, text: str) -> bool:
    """
    Sends a text message to a specified Telegram chat_id.
    """
    token = settings.telegram_bot_token
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not configured.")
        return False

    url = f"{TELEGRAM_API_BASE}{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                return True
            logger.error(f"Failed to send Telegram message: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error calling Telegram sendMessage API: {e}")
        return False


async def send_telegram_document(chat_id: int, file_path: str, caption: Optional[str] = None) -> bool:
    """
    Uploads and sends a document (PDF) to a specified Telegram chat_id.
    """
    token = settings.telegram_bot_token
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not configured.")
        return False

    if not os.path.exists(file_path):
        logger.error(f"File to send does not exist: {file_path}")
        return False

    url = f"{TELEGRAM_API_BASE}{token}/sendDocument"

    try:
        filename = os.path.basename(file_path)
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption

        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(file_path, "rb") as f:
                files = {"document": (filename, f, "application/pdf")}
                response = await client.post(url, data=data, files=files)
                if response.status_code == 200:
                    return True
                logger.error(f"Failed to send Telegram document: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"Error calling Telegram sendDocument API: {e}")
        return False
