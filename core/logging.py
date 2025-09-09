import sys
from loguru import logger
from config.config import settings

def setup_logging():
    logger.remove()
    
    # Console logging with proper encoding and null byte filtering
    logger.add(
        sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level=settings.LOG_LEVEL,
        backtrace=True,
        diagnose=True,
        encoding="utf-8",
        filter=lambda record: not any(ord(c) == 0 for c in str(record["message"])),  # Filter null bytes
    )
    
    # File logging with proper encoding
    logger.add(
        "logs/scraper.log",
        rotation="500 MB",
        retention="10 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level=settings.LOG_LEVEL,
        backtrace=True,
        diagnose=True,
        encoding="utf-8",
        filter=lambda record: not any(ord(c) == 0 for c in str(record["message"])),  # Filter null bytes
    )
    return logger