import chromadb
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
import os
from pathlib import Path
from urllib.parse import urlparse

from utils import (
    logger, validate_url, fetch_url_content, ContentType,
    EMBEDDING_CONFIGS, CHAT_CONFIGS, DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_CHAT_PROVIDER, ModelConfig
)
from model_providers import ModelFactory

class CustomEmbeddingFunction:
    """ChromaDB-compatible embedding function"""
    def __init__(self, provider):
        self.provider = provider

    def __call__(self, input: Union[str, List[str]]) -> List[List[float]]:
        """Generate embeddings for input text(s)"""
        if isinstance(input, str):
            input = [input]
        return self.provider.generate_embeddings(input)

class ContentManager:
    def __init__(self, embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER,
                 chat_provider: str = DEFAULT_CHAT_PROVIDER):
        """Initialize content manager with configurable model providers"""
        self.data_dir = Path("data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up model configurations
        self.embedding_config = EMBEDDING_CONFIGS[embedding_provider]
        self.chat_config = CHAT_CONFIGS[chat_provider]
        
        if self.embedding_config.api_key is None:
            self.embedding_config.api_key = os.getenv("OPENAI_API_KEY")
        if self.chat_config.api_key is None:
            self.chat_config.api_key = os.getenv("OPENAI_API_KEY")
        
        # Initialize model providers
        self.embedding_provider = ModelFactory.get_embedding_provider(self.embedding_config)
        self.chat_provider = ModelFactory.get_chat_provider(self.chat_config)
        
        # Initialize ChromaDB with custom embedding function
        self.client = chromadb.PersistentClient(path=str(self.data_dir / "chroma"))
        self.embedding_function = CustomEmbeddingFunction(self.embedding_provider)
        
        # Store active collections
        self.active_collections = self._load_collections()
        
        # Store provider info for UI
        self.current_embedding = embedding_provider
        self.current_chat = chat_provider

    def _load_collections(self) -> Dict:
        """Load existing collections"""
        collections = {}
        try:
            for name in self.client.list_collections():
                collection = self.client.get_collection(
                    name=name,
                    embedding_function=self.embedding_function
                )
                collections[name] = collection
        except Exception as e:
            logger.error(f"Error loading collections: {e}")
        return collections

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get basic statistics about collections"""
        stats = {
            "total_sources": len(self.active_collections),
            "content_types": {},
            "domains": {},
            "languages": {}
        }
        
        for collection in self.active_collections.values():
            meta = collection.metadata
            content_type = meta.get("content_type", "other")
            domain = meta.get("domain", "unknown")
            language = meta.get("language", "en")
            
            stats["content_types"][content_type] = stats["content_types"].get(content_type, 0) + 1
            stats["domains"][domain] = stats["domains"].get(domain, 0) + 1
            stats["languages"][language] = stats["languages"].get(language, 0) + 1
            
        return stats

    async def process_url(self, url: str, content_type: str) -> str:
        """Process URL and store content"""
        if not validate_url(url):
            raise ValueError("Invalid URL format")
            
        try:
            # Fetch content using eGet API
            data = await fetch_url_content(url)
            content_data = data["data"]
            
            # Create collection
            collection_id = f"url_{abs(hash(url))}"
            # Clean metadata - ensure no None values
            metadata = {
                "url": url,
                "title": str(content_data.get("metadata", {}).get("title") or "Untitled"),
                "content_type": str(content_type),
                "domain": str(urlparse(url).netloc),
                "language": str(content_data.get("metadata", {}).get("language") or "en"),
                "created_at": datetime.now().isoformat(),
                "description": str(content_data.get("metadata", {}).get("description") or ""),
                "status_code": int(content_data.get("metadata", {}).get("statusCode") or 200)
            }
            
            # Delete existing collection if it exists
            try:
                self.client.delete_collection(collection_id)
            except:
                pass
            
            collection = self.client.create_collection(
                name=collection_id,
                embedding_function=self.embedding_function,
                metadata=metadata
            )
            
            # Store content chunks
            text = content_data.get("markdown")
            if not text:
                raise ValueError("No content found in the response")
                
            chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
            
            for i, chunk in enumerate(chunks):
                collection.add(
                    documents=[chunk],
                    metadatas=[{"chunk_id": i}],
                    ids=[f"{collection_id}_chunk_{i}"]
                )
            
            self.active_collections[collection_id] = collection
            return collection_id
            
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            raise

    async def query_content(self, collection_id: str, query: str, n_results: int = 5) -> List[Dict]:
        """Query content with relevance and error handling.
        Retrieves more relevant chunks for better context."""
        try:
            collection = self.active_collections[collection_id]
            
            # Add retry logic for embedding operations
            max_retries = 3
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    # Query for more relevant chunks
                    results = collection.query(
                        query_texts=[query],
                        n_results=n_results,
                        # Include relevance scores
                        # include_distances=True
                    )
                    
                    # Process results with scores
                    context_entries = []
                    for doc, meta, distance in zip(
                        results["documents"][0],
                        results["metadatas"][0],
                        results["distances"][0]
                    ):
                        # Convert distance to similarity score (1 - normalized_distance)
                        score = 1 - (distance / max(results["distances"][0]))
                        
                        # Only include if relevance score is above threshold
                        if score >= 0.8:  # Adjust threshold as needed
                            context_entries.append({
                                "content": doc,
                                "metadata": meta,
                                "relevance_score": round(score, 3)
                            })
                    
                    # Return at least 3 results even if below threshold
                    return context_entries[:max(3, len(context_entries))]
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Embedding query failed, attempt {attempt + 1}/{max_retries}")
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                    raise
            
        except Exception as e:
            logger.error(f"Error querying content: {e}")
            # Return empty results instead of raising
            return [{"content": "Sorry, I couldn't process your query at the moment.", "metadata": {}}]

    async def get_chat_response( self, query: str, context_entries: List[Dict], chat_history: Optional[List[Dict]] = None ) -> Dict[str, Any]:
        """Generate chat response"""
        try:
            history = chat_history[-5:] if chat_history else []
            context = '\n\n'.join([f"[{i+1}] {entry['content']}" 
                                 for i, entry in enumerate(context_entries)])
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant that provides information based on the given context only. It is mandatory that you provide answers based on given text and nothing else. You are not allowed to lie or assume anything."},
                *[{"role": msg["role"], "content": msg["content"]} for msg in history],
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
            ]
            
            response = await self.chat_provider.generate_response(
                messages=messages,
                temperature=0.2
            )

            # Clean response content
            def clean_response(text: str) -> str:
                """Clean response by removing think tags and similar markup"""
                import re
                
                # Remove <think>...</think> tags and content
                text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
                
                # Remove other common AI markup patterns
                patterns = [
                    r'<antThinking>.*?</antThinking>',
                    r'<reasoning>.*?</reasoning>',
                    r'<thought>.*?</thought>',
                    r'<thinking>.*?</thinking>',
                    r'<internal>.*?</internal>',
                    r'\[thinking\].*?\[/thinking\]',
                    r'\[thought\].*?\[/thought\]'
                ]
                
                for pattern in patterns:
                    text = re.sub(pattern, '', text, flags=re.DOTALL)
                
                # Clean up extra whitespace
                text = re.sub(r'\n\s*\n', '\n\n', text)
                text = text.strip()
                
                return text
            
            return {
                "content": clean_response(response["content"]) ,# response["content"],
                "context_used": context_entries,
                "tokens": response["tokens"]
            }
            
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            raise