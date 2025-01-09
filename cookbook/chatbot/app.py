import streamlit as st
import json
import requests
from datetime import datetime
from typing import Dict, Any, List
from openai import OpenAI
import chromadb
from chromadb.utils import embedding_functions
import logging
from pathlib import Path
import os
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configure your OpenAI API key here
OPENAI_API_KEY = ""  # Add your API key here

# Ensure data directories exist
Path("data/chroma").mkdir(parents=True, exist_ok=True)

def chunk_text(text: str, chunk_size: int = 4000) -> List[str]:
    """Split text into smaller chunks"""
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0
    
    for word in words:
        current_size += len(word) + 1  # +1 for space
        if current_size > chunk_size:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_size = len(word) + 1
        else:
            current_chunk.append(word)
            
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

class ContentManager:
    def __init__(self):
        try:
            # Initialize ChromaDB
            self.client = chromadb.PersistentClient(path="data/chroma")
            
            # Initialize OpenAI embeddings
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=OPENAI_API_KEY,
                model_name="text-embedding-ada-002"
            )
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name="web_content",
                embedding_function=self.embedding_function
            )
            
            # Initialize OpenAI client
            self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
            
            logger.info("ContentManager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ContentManager: {e}", exc_info=True)
            raise

    def scrape_url(self, url: str) -> dict:
        """Scrape content from URL using eGet API"""
        try:
            response = requests.post(
                "http://localhost:8000/api/v1/scrape",
                json={
                    "url": url,
                    "onlyMainContent": True,
                    "formats": ["markdown"]
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if not data.get("success"):
                raise Exception(data.get("error", "Unknown error"))
                
            return data["data"]
            
        except requests.RequestException as e:
            logger.error(f"Failed to scrape {url}: {e}", exc_info=True)
            raise Exception(f"Failed to scrape {url}: {str(e)}")

    def add_content(self, url: str, content: dict) -> None:
        """Add content to ChromaDB"""
        try:
            # Chunk the markdown content
            text = content["markdown"]
            chunks = chunk_text(text)
            
            # Add each chunk as a separate document
            for i, chunk in enumerate(chunks):
                try:
                    self.collection.add(
                        documents=[chunk],
                        metadatas=[{
                            "url": url,
                            "title": content.get("metadata", {}).get("title", ""),
                            "timestamp": datetime.now().isoformat(),
                            "chunk": i
                        }],
                        ids=[f"{hash(url + datetime.now().isoformat())}_{i}"]
                    )
                except Exception as chunk_error:
                    logger.warning(f"Failed to add chunk {i} for {url}: {chunk_error}")
                    continue
                    
            logger.info(f"Content added for {url}")
            
        except Exception as e:
            logger.error(f"Failed to add content for {url}: {e}", exc_info=True)
            raise

    def get_relevant_content(self, query: str, n_results: int = 3) -> str:
        """Get relevant content for query"""
        try:
            if self.collection.count() == 0:
                return ""
                
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count())
            )
            
            if not results["documents"][0]:
                return ""
                
            # Combine context with source information
            context = []
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                context.append(f"Content from {meta['url']}:\n{doc}")
            
            return "\n\n".join(context)
            
        except Exception as e:
            logger.error(f"Failed to get relevant content: {e}", exc_info=True)
            raise

    def get_chat_response(self, query: str, context: str) -> str:
        """Get chat response using context"""
        try:
            # Truncate context if too long
            context_chunks = chunk_text(context, chunk_size=6000)  # Leave room for system and user message
            truncated_context = context_chunks[0] if context_chunks else ""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that answers questions based on the provided web content. If the context doesn't contain relevant information, say 'I don't know'."
                    },
                    {
                        "role": "user",
                        "content": f"Context:\n{truncated_context}\n\nQuestion: {query}"
                    }
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Failed to get chat response: {e}", exc_info=True)
            raise

def initialize_state():
    """Initialize Streamlit session state"""
    if 'content_manager' not in st.session_state:
        try:
            st.session_state.content_manager = ContentManager()
        except Exception as e:
            st.error(f"Failed to initialize: {str(e)}")
            return False
    
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
        
    if 'processed_urls' not in st.session_state:
        st.session_state.processed_urls = set()
    
    return True

def main():
    st.title("🌐 eGet Based RAG APP")
    
    if not OPENAI_API_KEY:
        st.error("Please set your OpenAI API key at the top of the script")
        return
        
    if not initialize_state():
        return

    # Sidebar
    with st.sidebar:
        st.header("📊 Statistics")
        total_docs = st.session_state.content_manager.collection.count()
        st.metric("Total Documents", total_docs)
        
        if st.session_state.processed_urls:
            st.subheader("Processed URLs")
            for url in st.session_state.processed_urls:
                st.text(url)
        
        st.subheader("🔧 Debug Options")
        show_context = st.checkbox("Show Context")
        show_time = st.checkbox("Show Response Time")

    # URL Input
    st.subheader("🌐 Add Web Content")
    urls_input = st.text_area(
        "Enter URLs (one per line):",
        help="Enter URLs to scrape and add to the knowledge base"
    )
    
    if st.button("Process URLs"):
        if urls_input:
            urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
            with st.spinner("Processing URLs..."):
                try:
                    for url in urls:
                        content = st.session_state.content_manager.scrape_url(url)
                        st.session_state.content_manager.add_content(url, content)
                        st.session_state.processed_urls.add(url)
                    st.success("URLs processed successfully!")
                    
                except Exception as e:
                    st.error(f"Error processing URLs: {str(e)}")

    # Chat Interface
    st.markdown("---")
    st.subheader("💬 Chat")
    
    # Display chat history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if show_context and message.get("context"):
                with st.expander("Context Used"):
                    st.text(message["context"])
            if show_time and message.get("response_time"):
                st.caption(f"Response time: {message['response_time']:.2f}s")

    # Chat input
    if query := st.chat_input("Ask about the web content"):
        # Add user message
        st.session_state.chat_history.append({
            "role": "user",
            "content": query
        })

        # Get response
        with st.spinner("Thinking..."):
            try:
                start_time = time.time()
                
                # Get relevant content
                context = st.session_state.content_manager.get_relevant_content(query)
                
                # Get response
                response = st.session_state.content_manager.get_chat_response(
                    query, context
                )
                
                # Add assistant message
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": response,
                    "context": context,
                    "response_time": time.time() - start_time
                })
                
                st.rerun()
                
            except Exception as e:
                st.error(f"Error: {str(e)}")

if __name__ == "__main__":
    main()