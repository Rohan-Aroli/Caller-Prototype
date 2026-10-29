from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    project_name: str = "AI Calling Platform"
    api_v1_str: str = "/api/v1"

settings = Settings()
