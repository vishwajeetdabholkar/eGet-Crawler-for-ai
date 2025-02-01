import streamlit as st
import asyncio
import os
from pathlib import Path

from utils import (
    check_eget_api, logger, DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_CHAT_PROVIDER
)
from content_manager import ContentManager
import ui

async def check_dependencies() -> bool:
    """Check if required services are available"""
    if not await check_eget_api():
        st.error("⚠️ eGet API is not available. Please ensure the service is running at localhost:8000")
        return False
    
    if not os.getenv("OPENAI_API_KEY"):
        st.error("⚠️ OpenAI API key not found. Please set the OPENAI_API_KEY environment variable")
        return False
    
    # Create necessary directories
    Path("data/chat_history").mkdir(parents=True, exist_ok=True)
    return True

def init_session_state():
    """Initialize session state variables"""
    if 'initialized' not in st.session_state:
        st.session_state.initialized = False
        st.session_state.content_manager = None
        st.session_state.active_url = None
        st.session_state.chat_history = {}
        st.session_state.view_mode = "Chat"
        st.session_state.embedding_provider = DEFAULT_EMBEDDING_PROVIDER
        st.session_state.chat_provider = DEFAULT_CHAT_PROVIDER

async def main():
    """Main application entry point"""
    st.title("🌐 Web Content Assistant")
    
    try:
        # Check dependencies
        if not await check_dependencies():
            return
        
        # Initialize session state
        init_session_state()
        
        # Initialize content manager if needed
        if not st.session_state.content_manager:
            st.session_state.content_manager = ContentManager(
                embedding_provider=st.session_state.embedding_provider,
                chat_provider=st.session_state.chat_provider
            )
        
        # Render sidebar
        await ui.render_sidebar(st.session_state.content_manager)
        
        # Main content area
        mode = st.radio("View Mode", ["Chat", "Analytics"], horizontal=True)
        
        if mode == "Analytics":
            ui.render_analytics()
        else:
            await ui.render_chat_interface()
            
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        st.error("An unexpected error occurred. Please refresh the page or contact support.")

if __name__ == "__main__":
    st.set_page_config(
        page_title="Web Content Assistant",
        page_icon="🌐",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    asyncio.run(main())
