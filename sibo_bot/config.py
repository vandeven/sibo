from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    allowed_telegram_user_ids: str = ""

    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"
    web_search_max_uses: int = 15

    search_radius_km: float = 2.0
    rate_limit_seconds: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_user_ids(self) -> frozenset[int]:
        """Parses the comma-separated whitelist; an empty set means everyone is allowed."""
        return frozenset(
            int(raw.strip()) for raw in self.allowed_telegram_user_ids.split(",") if raw.strip().isdigit()
        )


settings = Settings()
