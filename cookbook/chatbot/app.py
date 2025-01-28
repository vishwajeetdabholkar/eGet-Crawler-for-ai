import streamlit as st
import json
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
from openai import OpenAI
import chromadb
from chromadb.utils import embedding_functions
import logging
from pathlib import Path
import os
import time
import hashlib
from dataclasses import dataclass
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

@dataclass
class URLContent:
    """Data class to store URL content and metadata"""
    url: str
    content: str
    title: str
    timestamp: str
    domain: str
    collection_id: str

    @staticmethod
    def generate_collection_id(url: str) -> str:
        """Generate a unique collection ID for a URL"""
        domain = urlparse(url).netloc
        hash_object = hashlib.md5(url.encode())
        return f"{domain}_{hash_object.hexdigest()[:8]}"

class ContentManager:
    def __init__(self):
        """Initialize the content manager with dynamic collection support"""
        self.client = chromadb.PersistentClient(path="data/chroma")
        self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_name="text-embedding-ada-002"
        )
        self.openai_client = OpenAI()
        self.active_collections = {}
        self.load_existing_collections()

    def load_existing_collections(self):
        """Load existing collections from ChromaDB"""
        try:
            # In v0.6.0, list_collections returns only names
            collection_names = self.client.list_collections()
            for name in collection_names:
                try:
                    # Get each collection by name
                    collection = self.client.get_collection(
                        name=name,
                        embedding_function=self.embedding_function
                    )
                    self.active_collections[name] = collection
                except Exception as collection_error:
                    logger.error(f"Error loading collection {name}: {collection_error}")
                    continue
            
            logger.info(f"Loaded {len(self.active_collections)} existing collections")
        except Exception as e:
            logger.error(f"Error listing collections: {e}")
            # Initialize empty but don't fail
            self.active_collections = {}
    def get_or_create_collection(self, url: str) -> tuple[chromadb.Collection, str]:
        """Get existing collection or create new one for URL"""
        collection_id = URLContent.generate_collection_id(url)
        
        if collection_id not in self.active_collections:
            collection = self.client.create_collection(
                name=collection_id,
                embedding_function=self.embedding_function,
                metadata={"url": url, "created_at": datetime.now().isoformat()}
            )
            self.active_collections[collection_id] = collection
            logger.info(f"Created new collection for {url}")
        
        return self.active_collections[collection_id], collection_id

    def scrape_and_process_url(self, url: str) -> URLContent:
        """Scrape URL content and prepare for storage"""
        try:
            # Scrape content using eGet
            response = requests.post(
                "http://localhost:8000/api/v1/scrape",
                json={"url": url, "onlyMainContent": True, "formats": ["markdown"]},
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()["data"]
            
            return URLContent(
                url=url,
                content=data["markdown"],
                title=data.get("metadata", {}).get("title", "Unknown Title"),
                timestamp=datetime.now().isoformat(),
                domain=urlparse(url).netloc,
                collection_id=URLContent.generate_collection_id(url)
            )
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            raise

    def chunk_text(self, text: str, chunk_size: int = 4000) -> List[str]:
        """Split text into semantic chunks"""
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = []
        current_size = 0
        
        for paragraph in paragraphs:
            paragraph_size = len(paragraph)
            
            if current_size + paragraph_size > chunk_size:
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                current_chunk = [paragraph]
                current_size = paragraph_size
            else:
                current_chunk.append(paragraph)
                current_size += paragraph_size
        
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        return chunks

    def add_url_content(self, content: URLContent) -> None:
        """Add URL content to its collection"""
        try:
            collection, _ = self.get_or_create_collection(content.url)
            chunks = self.chunk_text(content.content)
            
            # Add chunks with metadata
            for i, chunk in enumerate(chunks):
                collection.add(
                    documents=[chunk],
                    metadatas=[{
                        "url": content.url,
                        "title": content.title,
                        "timestamp": content.timestamp,
                        "chunk_index": i,
                        "domain": content.domain
                    }],
                    ids=[f"{content.collection_id}_{i}"]
                )
            
            logger.info(f"Added {len(chunks)} chunks from {content.url}")
            
        except Exception as e:
            logger.error(f"Error adding content from {content.url}: {e}")
            raise

    def query_collection(self, collection_id: str, query: str, n_results: int = 3) -> List[Dict]:
        """Query specific collection for relevant content"""
        try:
            collection = self.active_collections.get(collection_id)
            if not collection:
                raise ValueError(f"Collection {collection_id} not found")
                
            results = collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            context_entries = []
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                context_entries.append({
                    "content": doc,
                    "metadata": meta
                })
                
            return context_entries
            
        except Exception as e:
            logger.error(f"Error querying collection {collection_id}: {e}")
            raise

    def get_chat_response(self, query: str, context_entries: List[Dict]) -> str:
        """Generate chat response using context"""
        try:
            # Format context for the prompt
            formatted_context = "\n\n".join([
                f"From {entry['metadata']['url']} ({entry['metadata']['title']}):\n{entry['content']}"
                for entry in context_entries
            ])
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a helpful assistant that provides accurate information based on the given web content.
                        Always cite your sources when providing information, and if information isn't available in the context, say so."""
                    },
                    {
                        "role": "user",
                        "content": f"Context:\n{formatted_context}\n\nQuestion: {query}"
                    }
                ],
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            raise

def initialize_state():
    """Initialize Streamlit session state"""
    if 'content_manager' not in st.session_state:
        st.session_state.content_manager = ContentManager()
    if 'active_url' not in st.session_state:
        st.session_state.active_url = None
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = {}

def main():
    st.title("🌐 Dynamic Web Content Assistant")
    
    initialize_state()

    # Sidebar for URL input and management
    with st.sidebar:
        st.header("📚 Knowledge Base")
        
        # URL Input
        url_input = st.text_input("Enter URL to analyze:")
        if st.button("Process URL", key="process_url"):
            if url_input:
                with st.spinner("Processing URL..."):
                    try:
                        # Scrape and process content
                        content = st.session_state.content_manager.scrape_and_process_url(url_input)
                        st.session_state.content_manager.add_url_content(content)
                        st.session_state.active_url = content.collection_id
                        
                        if content.collection_id not in st.session_state.chat_history:
                            st.session_state.chat_history[content.collection_id] = []
                        
                        st.success(f"Successfully processed: {content.title}")
                        
                    except Exception as e:
                        st.error(f"Error processing URL: {str(e)}")
        
        # Show available collections
        st.subheader("Available Sources")
        collections = st.session_state.content_manager.active_collections
        
        if collections:
            # Create a list of tuples with (collection_id, display_name)
            collection_options = []
            for coll_id, collection in collections.items():
                try:
                    # Get collection metadata safely
                    display_name = collection.metadata.get("url", coll_id) if collection.metadata else coll_id
                    collection_options.append((coll_id, display_name))
                except Exception as e:
                    logger.warning(f"Error getting metadata for collection {coll_id}: {e}")
                    collection_options.append((coll_id, coll_id))
            
            if collection_options:
                # Sort by display name for better UX
                collection_options.sort(key=lambda x: x[1])
                
                # Create radio options
                selected_collection = st.radio(
                    "Select source to chat with:",
                    options=[coll_id for coll_id, _ in collection_options],
                    format_func=lambda x: dict(collection_options)[x]
                )
                st.session_state.active_url = selected_collection
            else:
                st.info("No valid sources available. Add a URL to begin.")
        else:
            st.info("No sources available. Add a URL to begin.")

    # Main chat interface
    if st.session_state.active_url:
        st.subheader(f"💬 Chat with: {collections[st.session_state.active_url].metadata.get('url')}")
        
        # Display chat history
        history = st.session_state.chat_history.get(st.session_state.active_url, [])
        for message in history:
            with st.chat_message(message["role"]):
                st.write(message["content"])
                if message.get("context"):
                    with st.expander("📚 View Sources"):
                        for entry in message["context"]:
                            st.markdown(f"""
                            <div style="margin: 10px 0; padding: 10px; border-left: 3px solid #0066cc;">
                                <small style="color: #666;">
                                    Source: {entry['metadata']['url']}
                                    <br>Title: {entry['metadata']['title']}
                                </small>
                                <div style="margin-top: 5px;">{entry['content']}</div>
                            </div>
                            """, unsafe_allow_html=True)
        
        # Chat input
        if query := st.chat_input("Ask about the content..."):
            # Add user message
            history.append({"role": "user", "content": query})
            
            with st.spinner("Thinking..."):
                try:
                    # Get relevant context
                    context = st.session_state.content_manager.query_collection(
                        st.session_state.active_url,
                        query
                    )
                    
                    # Get response
                    response = st.session_state.content_manager.get_chat_response(query, context)
                    
                    # Add assistant message
                    history.append({
                        "role": "assistant",
                        "content": response,
                        "context": context
                    })
                    
                    st.session_state.chat_history[st.session_state.active_url] = history
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    else:
        st.info("👈 Enter a URL in the sidebar to begin chatting!")

if __name__ == "__main__":
    main()
