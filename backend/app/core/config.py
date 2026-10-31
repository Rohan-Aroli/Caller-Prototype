from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    project_name: str = "AI Calling Platform"
    api_v1_str: str = "/api/v1"
    max_upload_size_bytes: int = 10 * 1024 * 1024  # 10 MB default limit

    # Telephony configuration
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Gemini configuration
    GEMINI_API_KEY: str = ""

    # Server configuration for Ngrok/public access
    SERVER_DOMAIN: str = ""

settings = Settings()
