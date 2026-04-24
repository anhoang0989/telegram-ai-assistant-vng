from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str
    database_url: str
    encryption_key: str  # Fernet key for encrypting user API keys
    admin_user_id: int  # Telegram user_id của admin (approve/reject users)
    bot_mode: str = "polling"
    webhook_url: str = ""
    webhook_port: int = 8443
    scheduler_timezone: str = "Asia/Ho_Chi_Minh"

    llm_tier1: str = "gemini-2.5-flash-lite-preview-06-17"
    llm_tier2: str = "gemini-2.5-flash"
    llm_tier3: str = "gemini-2.5-pro"
    llm_tier4: str = "llama-3.3-70b-versatile"


settings = Settings()
