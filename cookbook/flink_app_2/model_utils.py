# model_utils.py
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

# Configure logging
logger = logging.getLogger("models")

class LLMProvider(ABC):
    """Abstract base class for language model providers."""
    
    @abstractmethod
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding vector for a text."""
        pass
    
    @abstractmethod
    def should_search_knowledge_base(self, query: str) -> Dict[str, Any]:
        """Determine if the query requires searching the knowledge base."""
        pass
    
    @abstractmethod
    def generate_response(self, query: str, context: Optional[str] = None) -> str:
        """Generate a response to a query, optionally with context."""
        pass

# Factory function to create LLM provider based on config
def create_llm_provider(config: Dict[str, Any]) -> LLMProvider:
    """Create an LLM provider instance based on configuration."""
    provider_type = config.get("llm_provider", "openai").lower()
    
    if provider_type == "openai":
        from openai_utils import OpenAIClient
        return OpenAIClient(config)
    elif provider_type == "anthropic":
        # In the future, you could add support for Anthropic
        logger.error("Anthropic provider not implemented yet")
        raise NotImplementedError("Anthropic provider not implemented yet")
    elif provider_type == "azure":
        # In the future, you could add support for Azure OpenAI
        logger.error("Azure OpenAI provider not implemented yet")
        raise NotImplementedError("Azure OpenAI provider not implemented yet")
    else:
        logger.error(f"Unknown LLM provider: {provider_type}")
        raise ValueError(f"Unknown LLM provider: {provider_type}")

def get_model_config(config: Dict[str, Any]) -> Dict[str, str]:
    """Get model configuration based on provider type."""
    provider_type = config.get("llm_provider", "openai").lower()
    
    if provider_type == "openai":
        return {
            "embedding_model": config.get("embedding_model", "text-embedding-ada-002"),
            "function_model": config.get("function_model", "gpt-4o"),
            "response_model": config.get("response_model", "gpt-4o-mini")
        }
    elif provider_type == "anthropic":
        return {
            "embedding_model": config.get("embedding_model", "text-embedding-ada-002"),  # OpenAI for embeddings
            "function_model": config.get("function_model", "claude-3-opus-20240229"),
            "response_model": config.get("response_model", "claude-3-haiku-20240307")
        }
    elif provider_type == "azure":
        return {
            "embedding_model": config.get("embedding_model", "text-embedding-ada-002"),
            "function_model": config.get("function_model", "gpt-4"),
            "response_model": config.get("response_model", "gpt-35-turbo")
        }
    else:
        # Default to OpenAI models
        return {
            "embedding_model": "text-embedding-ada-002",
            "function_model": "gpt-4o",
            "response_model": "gpt-4o-mini"
        }