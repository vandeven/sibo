import os
from typing import Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    gemini_api_key: str = ""
    telegram_webhook_secret: str = ""
    allowed_telegram_user_ids: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def allowed_user_ids_set(self) -> Set[int]:
        if not self.allowed_telegram_user_ids:
            return set()
        ids = set()
        for raw_id in self.allowed_telegram_user_ids.split(","):
            raw_id = raw_id.strip()
            if raw_id.isdigit():
                ids.add(int(raw_id))
        return ids


settings = Settings()
