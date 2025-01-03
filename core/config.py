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

    # Cache Settings
    REDIS_URL: str = "redis://redis:6379"
    CACHE_TTL: int = 86400  # 24 hours in seconds
    CACHE_ENABLED: bool = True

    # Document Converter Settings
    CONVERTER_MAX_FILE_SIZE_MB: int = int(os.getenv("CONVERTER_MAX_FILE_SIZE_MB", "5"))
    CONVERTER_CACHE_TTL: int = int(os.getenv("CONVERTER_CACHE_TTL", "3600"))
    CONVERTER_CONCURRENT_CONVERSIONS: int = int(os.getenv("CONVERTER_CONCURRENT_CONVERSIONS", "3"))
    CONVERTER_TIMEOUT: int = int(os.getenv("CONVERTER_TIMEOUT", "300"))

    # Converter Rate Limiting
    CONVERTER_RATE_LIMIT_ENABLED: bool = os.getenv("CONVERTER_RATE_LIMIT_ENABLED", "true").lower() == "true"
    CONVERTER_RATE_LIMIT_REQUESTS: int = int(os.getenv("CONVERTER_RATE_LIMIT_REQUESTS", "50"))
    CONVERTER_RATE_LIMIT_PERIOD: int = int(os.getenv("CONVERTER_RATE_LIMIT_PERIOD", "3600"))

    # Converter Image Settings
    CONVERTER_IMAGE_QUALITY: int = int(os.getenv("CONVERTER_IMAGE_QUALITY", "80"))
    CONVERTER_MAX_IMAGE_SIZE_MB: int = int(os.getenv("CONVERTER_MAX_IMAGE_SIZE_MB", "2"))
    CONVERTER_STORE_IMAGES: bool = os.getenv("CONVERTER_STORE_IMAGES", "true").lower() == "true"
    CONVERTER_IMAGE_STORAGE_PATH: str = os.getenv("CONVERTER_IMAGE_STORAGE_PATH", "/app/data/images")

    # Format-Specific Settings
    CONVERTER_PDF_EXTRACT_IMAGES: bool = os.getenv("CONVERTER_PDF_EXTRACT_IMAGES", "true").lower() == "true"
    CONVERTER_PDF_DETECT_TABLES: bool = os.getenv("CONVERTER_PDF_DETECT_TABLES", "true").lower() == "true"
    CONVERTER_DOCX_PRESERVE_FORMATTING: bool = os.getenv("CONVERTER_DOCX_PRESERVE_FORMATTING", "true").lower() == "true"
    CONVERTER_XLSX_MAX_ROWS: int = int(os.getenv("CONVERTER_XLSX_MAX_ROWS", "10000"))
    CONVERTER_PPTX_INCLUDE_NOTES: bool = os.getenv("CONVERTER_PPTX_INCLUDE_NOTES", "true").lower() == "true"

    # Converter Cache Settings
    CONVERTER_CACHE_ENABLED: bool = os.getenv("CONVERTER_CACHE_ENABLED", "true").lower() == "true"
    CONVERTER_CACHE_KEY_PREFIX: str = os.getenv("CONVERTER_CACHE_KEY_PREFIX", "converter")
    CONVERTER_CACHE_COMPRESS: bool = os.getenv("CONVERTER_CACHE_COMPRESS", "true").lower() == "true"


    class Config:
        env_file = ".env"
        case_sensitive = True

        @classmethod
        def parse_env_var(cls, field_name: str, raw_val: str) -> Any:
            """Custom parsing for environment variables"""
            if field_name == "ALLOWED_HOSTS":
                if raw_val == "*":
                    return ["*"]
                return raw_val.split(",")
            return cls.json_loads(raw_val)  # type: ignore

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings to avoid loading .env file multiple times"""
    return Settings()

settings = get_settings()