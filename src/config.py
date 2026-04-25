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

    # Tier order: workhorse free-tier → backup free-tier → cross-provider → paid-only
    # ⚠️ Tên model ID phải match Google API. Check log lúc startup để xem list_models()
    # và override qua env vars LLM_TIER1..LLM_TIER7 nếu sai.
    llm_tier1: str = "gemini-3.1-flash-lite-preview"  # 15 RPM / 500 RPD — workhorse
    llm_tier2: str = "gemini-2.5-flash-lite"          # 10 RPM / 20 RPD
    llm_tier3: str = "gemini-3-flash-preview"         # 5 RPM / 20 RPD — reasoning
    llm_tier4: str = "gemini-2.5-flash"               # 5 RPM / 20 RPD
    llm_tier5: str = "llama-3.3-70b-versatile"        # Groq cross-provider
    llm_tier6: str = "gemini-3.1-pro-preview"         # Paid only
    llm_tier7: str = "gemini-2.5-pro"                 # Paid only


settings = Settings()
