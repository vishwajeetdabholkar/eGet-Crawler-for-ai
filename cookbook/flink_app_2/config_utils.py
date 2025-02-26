# config_utils.py
import json
import logging
from pathlib import Path
from typing import Dict, Any

# Configure logging
logger = logging.getLogger("config")

def create_default_config(config_path: Path) -> None:
    """Create a default configuration file if none exists."""
    default_config = {
        "kafka_bootstrap_servers": "pkc-...:9092",
        "kafka_api_key": "YOUR_API_KEY",
        "kafka_api_secret": "YOUR_API_SECRET",
        "kafka_topic": "website_chunks",
        "schema_registry_url": "https://psrc-...",
        "schema_registry_api_key": "YOUR_SR_API_KEY",
        "schema_registry_api_secret": "YOUR_SR_API_SECRET",
        "openai_api_key": "YOUR_OPENAI_API_KEY",
        "mongodb_uri": "mongodb+srv://user:pass@cluster...",
        "mongodb_database": "documentation",
        "mongodb_collection": "chunks",
        "chunker_api_url": "https://your-chunker-api-url.com/chunk"
    }
    
    try:
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        logger.info(f"Created default configuration at {config_path}")
    except Exception as e:
        logger.error(f"Error creating default config: {str(e)}")
        raise

def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Load configuration from JSON file."""
    try:
        config_path = Path(config_path)
        if not config_path.exists():
            create_default_config(config_path)
            
        with open(config_path, 'r') as f:
            config = json.load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config
    except Exception as e:
        logger.error(f"Error loading config from {config_path}: {str(e)}")
        raise RuntimeError(f"Could not load config: {str(e)}")