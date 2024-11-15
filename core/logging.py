import sys
from loguru import logger
from config.config import settings

def setup_logging():
    logger.remove()
    logger.add(
        sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level=settings.LOG_LEVEL,
        backtrace=True,
        diagnose=True,
    )
    logger.add(
        "logs/scraper.log",
        rotation="500 MB",
        retention="10 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level=settings.LOG_LEVEL,
        backtrace=True,
        diagnose=True,
    )
    return logger