from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    project_name: str = "AI Calling Platform"
    api_v1_str: str = "/api/v1"
    max_upload_size_bytes: int = 10 * 1024 * 1024  # 10 MB default limit

    # Telephony configuration
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # AI & Speech Providers
    GEMINI_API_KEY: str = ""
    DEEPGRAM_API_KEY: str = ""
    DEEPGRAM_VOICE_MODEL: str = "aura-asteria-en"  # Natural Deepgram Aura voice

    # Server configuration for Ngrok/public access (without https://)
    SERVER_DOMAIN: str = ""

    # Optional signature validation toggle (default True in production, can disable if testing locally without webhook signatures)
    VERIFY_TWILIO_SIGNATURE: bool = True

settings = Settings()
