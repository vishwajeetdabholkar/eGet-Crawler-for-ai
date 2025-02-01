from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum
import logging
from urllib.parse import urlparse
import aiohttp
import json
from dataclasses import dataclass

# API configurations
EGET_API_URL = "http://localhost:8000"
EGET_API_TIMEOUT = 30

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('app.log')]
)
logger = logging.getLogger(__name__)

class ContentType(Enum):
    """Content types supported by the application"""
    ARTICLE = "article"
    BLOG = "blog"
    DOCUMENTATION = "documentation"
    RESEARCH = "research"
    OTHER = "other"

class ModelProvider(Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"  # For future use

@dataclass
class ModelConfig:
    provider: ModelProvider
    model_name: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.2
    extra_params: Optional[Dict[str, Any]] = None

# Model configurations
EMBEDDING_CONFIGS = {
    "openai": ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="text-embedding-ada-002",
        api_key=None  # Will be set from environment
    ),
    "ollama": ModelConfig(
        provider=ModelProvider.OLLAMA,
        model_name="nomic-embed-text",
        api_base="http://localhost:11434"
    )
}

CHAT_CONFIGS = {
    "openai": ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-4o-mini",
        api_key=None
    ),
    "ollama": ModelConfig(
        provider=ModelProvider.OLLAMA,
        model_name="deepseek-r1",
        api_base="http://localhost:11434"
    )
}

# Default selections
DEFAULT_EMBEDDING_PROVIDER = "ollama"
DEFAULT_CHAT_PROVIDER = "openai"

async def check_eget_api() -> bool:
    """Check if eGet API is available"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{EGET_API_URL}/health") as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"eGet API health check failed: {e}")
        return False

def validate_url(url: str) -> bool:
    """Validate URL format and scheme"""
    try:
        result = urlparse(url)
        return all([result.scheme in ('http', 'https'), result.netloc])
    except Exception:
        return False

async def fetch_url_content(url: str) -> Dict[str, Any]:
    """Fetch content from URL using eGet API"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{EGET_API_URL}/api/v1/scrape",
            json={
                "url": url,
                "onlyMainContent": True,
                "formats": ["markdown", "html"],
                "includeStructuredData": True,
                "includeScreenshot": True
            },
            timeout=EGET_API_TIMEOUT
        ) as response:
            response.raise_for_status()
            return await response.json()

def format_chat_context(context_entries: List[Dict]) -> str:
    """Format context entries for chat"""
    formatted = []
    for i, entry in enumerate(context_entries, 1):
        meta = entry["metadata"]
        formatted.append(f"[{i}] From {meta['title']}:\n{entry['content']}\n")
    return "\n\n".join(formatted)

def save_chat_history(collection_id: str, history: List[Dict]) -> None:
    """Save chat history to disk"""
    try:
        with open(f"data/chat_history/{collection_id}.json", 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving chat history: {e}")

async def load_chat_history(collection_id: str) -> List[Dict]:
    """Load chat history from disk"""
    try:
        with open(f"data/chat_history/{collection_id}.json", 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.error(f"Error loading chat history: {e}")
        return []