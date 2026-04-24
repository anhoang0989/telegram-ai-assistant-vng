from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str
    allowed_user_ids: str  # comma-separated
    gemini_api_key: str
    groq_api_key: str
    database_url: str
    bot_mode: str = "polling"
    webhook_url: str = ""
    webhook_port: int = 8443
    scheduler_timezone: str = "Asia/Ho_Chi_Minh"

    # Model names — configurable so free-tier names can be updated without code changes
    model_tier1: str = "gemini-2.5-flash-lite-preview-06-17"
    model_tier2: str = "gemini-2.5-flash"
    model_tier3: str = "gemini-2.5-pro"
    model_tier4: str = "llama-3.3-70b-versatile"  # Groq

    @property
    def allowed_user_ids_list(self) -> list[int]:
        return [int(uid.strip()) for uid in self.allowed_user_ids.split(",") if uid.strip()]


settings = Settings()
