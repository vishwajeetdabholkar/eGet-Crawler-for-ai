from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import ollama
from openai import OpenAI
import asyncio
from utils import ModelConfig, logger

class EmbeddingProvider(ABC):
    @abstractmethod
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        pass

class ChatProvider(ABC):
    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        pass

class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, config: ModelConfig):
        self.config = config

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            try:
                response = ollama.embeddings(
                    model=self.config.model_name,
                    prompt=text
                )
                embeddings.append(response.embedding)
            except Exception as e:
                logger.error(f"Ollama embedding error: {e}")
                embeddings.append([0.0] * 512)
        return embeddings

class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, config: ModelConfig):
        self.client = OpenAI(api_key=config.api_key)
        self.config = config

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        try:
            response = self.client.embeddings.create(
                model=self.config.model_name,
                input=texts
            )
            return [e.embedding for e in response.data]
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            return [[0.0] * 1536] * len(texts)

class OllamaChatProvider(ChatProvider):
    def __init__(self, config: ModelConfig):
        self.config = config

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        try:
            # Convert messages to prompt
            prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ollama.chat(
                    model=self.config.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": temperature}
                )
            )
            
            return {
                "content": response.message.content,
                "tokens": {
                    "prompt": 0,  # Ollama doesn't provide token counts
                    "completion": 0,
                    "total": 0
                }
            }
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            raise

class OpenAIChatProvider(ChatProvider):
    def __init__(self, config: ModelConfig):
        self.client = OpenAI(api_key=config.api_key)
        self.config = config

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.config.model_name,
                    messages=messages,
                    temperature=temperature
                )
            )
            
            return {
                "content": response.choices[0].message.content,
                "tokens": {
                    "prompt": response.usage.prompt_tokens,
                    "completion": response.usage.completion_tokens,
                    "total": response.usage.total_tokens
                }
            }
        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
            raise

class ModelFactory:
    @staticmethod
    def get_embedding_provider(config: ModelConfig) -> EmbeddingProvider:
        if config.provider.value == "ollama":
            return OllamaEmbeddingProvider(config)
        elif config.provider.value == "openai":
            return OpenAIEmbeddingProvider(config)
        else:
            raise ValueError(f"Unsupported embedding provider: {config.provider}")

    @staticmethod
    def get_chat_provider(config: ModelConfig) -> ChatProvider:
        if config.provider.value == "ollama":
            return OllamaChatProvider(config)
        elif config.provider.value == "openai":
            return OpenAIChatProvider(config)
        else:
            raise ValueError(f"Unsupported chat provider: {config.provider}")