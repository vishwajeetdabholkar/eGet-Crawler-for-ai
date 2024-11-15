from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # API Settings
    DEBUG: bool = False
    PORT: int = 8000
    WORKERS: int = 4
    LOG_LEVEL: str = "INFO"
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Web Scraper API"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ALLOWED_HOSTS: List[str] = ["*"]

    # Scraper Settings
    MAX_WORKERS: int = 5  # Maximum number of browser instances
    TIMEOUT: int = 30000  # in milliseconds
    MAX_RETRIES: int = 3
    CONCURRENT_SCRAPES: int = 10
    DEFAULT_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    SCREENSHOT_QUALITY: int = 80

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings to avoid loading .env file multiple times"""
    return Settings()

settings = get_settings()