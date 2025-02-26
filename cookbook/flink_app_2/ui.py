# ui.py
import asyncio
import logging
import streamlit as st
from pathlib import Path

# Import from modular utilities
from config_utils import load_config
from kafka_utils import process_url_and_send_to_kafka
from openai_utils import ConfluentRAG
from db_utils import get_stored_urls, store_processed_url

# Configure logging for UI components
logger = logging.getLogger("ui")

def create_streamlit_app():
    """Create and configure the Streamlit app with integrated chunker and RAG assistant."""
    
    st.set_page_config(
        page_title="Confluent Documentation Tools",
        page_icon="💬",
        layout="wide"
    )
    
    # Initialize RAG system
    try:
        if 'rag' not in st.session_state:
            st.session_state.rag = ConfluentRAG()
            st.session_state.config = load_config()
    except Exception as e:
        st.error(f"Failed to initialize the application: {str(e)}")
        return
    
    # Initialize chat history if it doesn't exist
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    # Create tabs for different functionalities
    tab1, tab2, tab3 = st.tabs(["Documentation Assistant", "URL Chunker", "Processed URLs"])
    
    # Tab 1: Documentation Assistant
    with tab1:
        st.title("Confluent Documentation Assistant using eGet-crawler-for-ai")
        st.markdown("Ask me anything about Confluent documentation!")
        
        # Display chat history
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # Chat input
        if prompt := st.chat_input("Ask your question about Confluent..."):
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Generate and display assistant response
            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                with st.spinner("Processing your question... This may take a moment"):
                    try:
                        # Show a temporary "thinking" message
                        response_placeholder.markdown("_Thinking..._")
                        
                        # Get the actual response
                        response = st.session_state.rag.answer_question(prompt)
                        
                        # Replace the temporary message with the final response
                        response_placeholder.markdown(response)
                        
                        # Add assistant response to chat history
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    except Exception as e:
                        error_message = "I'm sorry, I encountered an error while processing your question."
                        response_placeholder.markdown(error_message)
                        logger.error(f"Error processing question: {str(e)}")
                        st.session_state.messages.append({"role": "assistant", "content": error_message})
        
        # Sidebar for documentation assistant
        with st.sidebar:
            st.header("Assistant Options")
            
            # Chat history management
            if st.button("Clear Chat History"):
                st.session_state.messages = []
                st.rerun()
            
            # About section
            st.markdown("---")
            st.markdown("### About")
            st.markdown("""
            This assistant uses Retrieval-Augmented Generation (RAG) to provide accurate answers to your questions about Confluent.
            
            It only searches the knowledge base when necessary and can answer general questions without looking up information.
            """)
    
    # Tab 2: URL Chunker
    with tab2:
        st.title("URL Chunker and Kafka Streamer")
        st.markdown("Enter a URL to chunk the content and stream it to Kafka")
        
        # URL input
        url_input = st.text_input(
            "URL", 
            placeholder="https://example.com",
            help="Enter the full URL to process"
        )
        
        # Chunker options
        col1, col2 = st.columns([3, 1])
        with col1:
            chunker_type = st.selectbox(
                "Chunker Type",
                options=["sentence", "semantic"],
                index=0,
                help="Choose chunking algorithm"
            )
        
        with col2:
            submit_btn = st.button("Process URL", type="primary", use_container_width=True)
        
        # Output area
        chunks_output = st.empty()
        
        # Process URL when button is clicked
        if submit_btn and url_input:
            if not url_input.startswith(("http://", "https://")):
                chunks_output.error("Please enter a valid URL starting with http:// or https://")
            else:
                try:
                    with st.spinner("Processing URL... This may take a moment"):
                        # Process URL
                        result = asyncio.run(process_url_and_send_to_kafka(url_input, st.session_state.config, chunker_type))
                        
                        if not result or not result.get("success"):
                            error_msg = result.get("error") if result else "Unknown error"
                            chunks_output.error(f"Error processing URL: {error_msg}")
                        else:
                            # Format chunks for display
                            chunks = result.get("chunks", [])
                            if not chunks:
                                chunks_output.warning("No chunks found in the processed URL")
                            else:
                                # Create formatted output
                                output_md = f"## Processed {url_input}\n"
                                output_md += f"### Found {len(chunks)} chunks\n\n"
                                
                                for i, chunk in enumerate(chunks):
                                    output_md += f"#### Chunk {i+1}/{len(chunks)}\n"
                                    output_md += f"**Type:** {chunk.get('type', 'text')}  \n"
                                    output_md += f"**Words:** {chunk.get('metadata', {}).get('word_count', 0)}  \n"
                                    output_md += f"**Content:**  \n```\n{chunk.get('content', '')}\n```\n\n"
                                
                                chunks_output.markdown(output_md)
                                
                                # Store the processed URL in the database
                                store_processed_url(url_input, chunker_type, len(chunks))
                                
                except Exception as e:
                    logger.error(f"Error in URL processing: {str(e)}", exc_info=True)
                    chunks_output.error(f"An error occurred: {str(e)}")
    
    # Tab 3: Processed URLs
    with tab3:
        st.title("Processed URLs")
        st.markdown("View all previously processed URLs")
        
        # Add a refresh button
        if st.button("Refresh URL List", key="refresh_urls"):
            st.experimental_rerun()
            
        # Get and display stored URLs
        try:
            urls = get_stored_urls()
            if not urls:
                st.info("No URLs have been processed yet.")
            else:
                # Create a table of processed URLs
                st.markdown("### Previously Processed URLs")
                
                # Create columns for the table
                columns = st.columns([3, 1, 1, 2])
                columns[0].markdown("**URL**")
                columns[1].markdown("**Chunker Type**")
                columns[2].markdown("**Chunks**")
                columns[3].markdown("**Processed At**")
                
                # Add a separator
                st.markdown("---")
                
                # Display each URL in a row
                for url in urls:
                    cols = st.columns([3, 1, 1, 2])
                    cols[0].markdown(f"[{url['url']}]({url['url']})")
                    cols[1].markdown(f"{url['chunker_type']}")
                    cols[2].markdown(f"{url['chunk_count']}")
                    cols[3].markdown(f"{url['processed_at']}")
        except Exception as e:
            logger.error(f"Error retrieving stored URLs: {str(e)}")
            st.error("Failed to load processed URLs.")