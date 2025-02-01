import streamlit as st
import plotly.express as px
from utils import (
    ContentType, save_chat_history, load_chat_history, logger,
    EMBEDDING_CONFIGS, CHAT_CONFIGS, DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_CHAT_PROVIDER
)
from content_manager import ContentManager

def render_model_settings():
    """Render model selection settings"""
    st.sidebar.subheader("🤖 Model Settings")
    
    # Select embedding model
    embedding_provider = st.sidebar.selectbox(
        "Embedding Model",
        options=list(EMBEDDING_CONFIGS.keys()),
        format_func=lambda x: f"{x.title()} ({EMBEDDING_CONFIGS[x].model_name})",
        key="embedding_provider",
        index=list(EMBEDDING_CONFIGS.keys()).index(DEFAULT_EMBEDDING_PROVIDER)
    )
    
    # Select chat model
    chat_provider = st.sidebar.selectbox(
        "Chat Model",
        options=list(CHAT_CONFIGS.keys()),
        format_func=lambda x: f"{x.title()} ({CHAT_CONFIGS[x].model_name})",
        key="chat_provider",
        index=list(CHAT_CONFIGS.keys()).index(DEFAULT_CHAT_PROVIDER)
    )
    
    # Apply changes button
    if st.sidebar.button("Apply Model Changes"):
        with st.spinner("Reinitializing models..."):
            try:
                st.session_state.content_manager = ContentManager(
                    embedding_provider=embedding_provider,
                    chat_provider=chat_provider
                )
                st.success("Models updated successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Error updating models: {str(e)}")

async def render_sidebar(content_manager):
    """Render sidebar with controls"""
    with st.sidebar:
        st.header("📚 Web Content Assistant Using eGet-CrawlerForAi")
        
        # Model settings
        render_model_settings()
        
        # Add new URL
        st.subheader("Add New Content")
        url = st.text_input("Enter URL:")
        content_type = st.selectbox(
            "Content Type",
            options=[ct.value for ct in ContentType],
            format_func=lambda x: x.capitalize()
        )
        
        if st.button("Process URL"):
            if url:
                with st.spinner("Processing URL..."):
                    try:
                        collection_id = await content_manager.process_url(url, content_type)
                        st.session_state.active_url = collection_id
                        st.success("URL processed successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        
        # Show available sources
        st.subheader("Available Sources")
        if content_manager.active_collections:
            for coll_id, collection in content_manager.active_collections.items():
                if st.button(
                    f"📄 {collection.metadata.get('title', 'Untitled')}",
                    key=f"source_{coll_id}"
                ):
                    st.session_state.active_url = coll_id
                    st.rerun()
        else:
            st.info("No sources available. Add a URL to begin.")

def render_analytics():
    """Render analytics dashboard"""
    st.subheader("📊 Content Analytics")
    
    stats = st.session_state.content_manager.get_collection_stats()
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Sources", stats["total_sources"])
    with col2:
        st.metric("Content Types", len(stats["content_types"]))
    with col3:
        st.metric("Domains", len(stats["domains"]))
    
    # Visualizations
    if stats["total_sources"] > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            fig = px.pie(
                names=list(stats["content_types"].keys()),
                values=list(stats["content_types"].values()),
                title="Content Types Distribution"
            )
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            fig = px.pie(
                names=list(stats["domains"].keys()),
                values=list(stats["domains"].values()),
                title="Domain Distribution"
            )
            st.plotly_chart(fig, use_container_width=True)

async def handle_chat_input(history):
    """Handle chat input and return updated history"""
    if query := st.chat_input("Ask about the content..."):
        history.append({"role": "user", "content": query})
        
        with st.spinner("Thinking..."):
            try:
                # Get relevant context
                context = await st.session_state.content_manager.query_content(
                    st.session_state.active_url,
                    query
                )
                
                # Get response
                response = await st.session_state.content_manager.get_chat_response(
                    query,
                    context,
                    chat_history=history[-5:]
                )
                
                # Add to history
                history.append({
                    "role": "assistant",
                    "content": response["content"],
                    "context": response["context_used"],
                    "tokens": response["tokens"]
                })
                
                # Save history
                save_chat_history(st.session_state.active_url, history)
                st.rerun()
                
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    return history

async def render_chat_interface():
    """Render chat interface"""
    if not st.session_state.get("active_url"):
        st.info("👈 Select a source from the sidebar to start chatting!")
        return
        
    collection = st.session_state.content_manager.active_collections[st.session_state.active_url]
    
    # Show current models
    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"🧮 Using {st.session_state.embedding_provider.title()} embeddings")
    with col2:
        st.caption(f"💭 Using {st.session_state.chat_provider.title()} chat")
    
    st.subheader(f"💬 Chat with: {collection.metadata.get('title')}")
    
    # Load chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = {}
    
    if st.session_state.active_url not in st.session_state.chat_history:
        st.session_state.chat_history[st.session_state.active_url] = []
    
    # Display chat history
    history = st.session_state.chat_history[st.session_state.active_url]
    for message in history:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if message.get("context"):
                with st.expander("View Sources"):
                    for entry in message["context"]:
                        st.markdown(f"**Source:** {entry['metadata'].get('title')}")
                        st.markdown(entry["content"])
    
    # Handle chat input
    updated_history = await handle_chat_input(history)
    st.session_state.chat_history[st.session_state.active_url] = updated_history
    
    # Chat controls
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Clear History"):
            st.session_state.chat_history[st.session_state.active_url] = []
            save_chat_history(st.session_state.active_url, [])
            st.rerun()
            
    with col2:
        if st.button("Save History"):
            save_chat_history(st.session_state.active_url, updated_history)
            st.success("Chat history saved!")