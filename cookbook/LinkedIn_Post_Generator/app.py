import streamlit as st
import requests
import json
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from datetime import datetime
import os
from pathlib import Path
import logging
from openai import OpenAI
from together import Together

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('linkedin_generator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AiProvider:
    """Base class for AI providers"""
    def generate_post(self, content: str, url: str) -> Optional[str]:
        raise NotImplementedError

class TogetherAiProvider(AiProvider):
    def __init__(self, api_key: str):
        self.client = Together(api_key=api_key)
        self.model = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    
    def generate_post(self, content: str, url: str) -> Optional[str]:
        try:
            prompt = f"""Create an outstanding LinkedIn post about the following content.
            
            Key requirements:
            0. No markdown format output.
            1. Start with a powerful hook that grabs attention .
            2. Use 2-3 relevant emojis strategically placed
            3. Break content into 2-3 easy-to-read paragraphs
            4. Keep it to the point, a post is supposed to get people excited in 1 minute or less time read to checkout the actual content.
            5. Add the source URL at the end
            6. Always return only POST. do not stretch it much, its post not a blog.
            7. the post has to sound human no matter what, you can always make it a bit sarcastic too.
            
            Content: {content}
            URL: {url}
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert LinkedIn content creator known for writing viral, engaging posts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Together.ai API error: {str(e)}")
            return None

class OllamaProvider(AiProvider):
    def __init__(self):
        self.client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
        
    def generate_post(self, content: str, url: str) -> Optional[str]:
        try:
            prompt = f"""Create an outstanding LinkedIn post about the following content.
            
            Key requirements:
            0. No markdown format output.
            1. Start with a powerful hook that grabs attention
            2. Use 2-3 relevant emojis strategically placed
            3. Break content into 2-3 easy-to-read paragraphs
            4. Include a thought-provoking question or call-to-action
            5. Add the source URL at the end
            6. Always return only POST. do not stretch it much, its post not a blog.
            
            Content: {content}
            URL: {url}
            """
            
            response = self.client.chat.completions.create(
                model="llama3.2",
                messages=[
                    {"role": "system", "content": "You are an expert LinkedIn content creator known for writing viral, engaging posts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Ollama API error: {str(e)}")
            return None

class OpenAIProvider(AiProvider):
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        
    def generate_post(self, content: str, url: str) -> Optional[str]:
        try:
            prompt = f"""Create an outstanding LinkedIn post about the following content.
            
            Key requirements:
            1. Start with a powerful hook that grabs attention
            2. Use 2-3 relevant emojis strategically placed
            3. Break content into 2-3 easy-to-read paragraphs
            4. Include a thought-provoking question or call-to-action
            5. Add the source URL at the end
            6. Do not use markdown format, Linkedin does not allow that.
            7. Direclty start writing post, nothing else.
            
            Content: {content}
            URL: {url}
            """
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert LinkedIn content creator known for writing viral, engaging posts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return None

class ScraperAPI:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def scrape_url(self, url: str) -> Optional[str]:
        logger.info(f"Starting to scrape URL: {url}")
        try:
            response = requests.post(
                f"{self.base_url}/scrape",
                json={"url": url, "onlyMainContent": True, "formats": ["markdown"]},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data["success"] and data["data"]["markdown"]:
                content_length = len(data["data"]["markdown"])
                logger.info(f"Successfully scraped {url}. Content length: {content_length} characters")
                return data["data"]["markdown"]
            else:
                error = data.get('data', {}).get('metadata', {}).get('error')
                logger.error(f"Failed to get content from {url}: {error}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Request error for {url}: {str(e)}")
            return None

def get_ai_provider(provider_name: str, api_key: Optional[str] = None) -> AiProvider:
    if provider_name == "Together.ai":
        return TogetherAiProvider(api_key)
    elif provider_name == "Ollama":
        return OllamaProvider()
    elif provider_name == "OpenAI":
        return OpenAIProvider(api_key)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")

def init_session_state():
    if 'posts_generated' not in st.session_state:
        st.session_state.posts_generated = 0

def main():
    st.set_page_config(page_title="LinkedIn Post Generator", page_icon="✍️", layout="wide")
    
    # Custom CSS (same as before)
    st.markdown("""
        <style>
        .stApp {
            background-color: #1E1E1E;
            color: #FFFFFF;
        }
        .post-container {
            background-color: #2D2D2D;
            padding: 2.5rem;
            border-radius: 15px;
            border: 1px solid #404040;
            margin: 1rem 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.6;
            font-size: 16px;
            white-space: pre-line;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 2rem;
            padding: 2rem;
            background: linear-gradient(135deg, #0A66C2 0%, #004182 100%);
            border-radius: 15px;
            box-shadow: 0 4px 12px rgba(10, 102, 194, 0.2);
        }
        /* ... (rest of the CSS) ... */
        </style>
    """, unsafe_allow_html=True)
    
    init_session_state()
    
    # Header
    st.markdown('<div class="header">', unsafe_allow_html=True)
    st.title("✍️ LinkedIn Post Generator")
    st.markdown("Transform any webpage into an engaging LinkedIn post with AI")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # AI Provider Selection
    ai_provider_name = st.sidebar.selectbox(
        "Select AI Provider",
        ["Together.ai", "Ollama", "OpenAI"],
        index=0
    )
    
    # API Key Input based on provider
    api_key = None
    if ai_provider_name in ["Together.ai", "OpenAI"]:
        api_key = st.sidebar.text_input(
            f"Enter {ai_provider_name} API Key",
            type="password",
            key=f"{ai_provider_name}_api_key"
        )
        
        if not api_key:
            st.sidebar.warning(f"Please enter your {ai_provider_name} API key to continue.")
            return
    
    # Initialize components
    scraper = ScraperAPI()
    ai_provider = get_ai_provider(ai_provider_name, api_key)
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        url = st.text_input(
            "Enter webpage URL:",
            placeholder="https://example.com",
            help="Enter the URL of the webpage you want to create a post about"
        )
        
        if url:
            if not url.startswith(('http://', 'https://')):
                st.error("Please enter a valid URL starting with http:// or https://")
            else:
                try:
                    urlparse(url)
                    if st.button("Generate Post 🚀"):
                        with st.spinner("Reading webpage content..."):
                            content = scraper.scrape_url(url)
                            
                            if not content:
                                st.error("Failed to fetch webpage content. Please check if the URL is accessible.")
                            else:
                                with st.spinner(f"Generating post using {ai_provider_name}..."):
                                    post = ai_provider.generate_post(content, url)
                                    
                                    if post:
                                        st.session_state.posts_generated += 1
                                        
                                        # Display the post with LinkedIn-style formatting
                                        formatted_post = post.replace('\n', '<br>')
                                        st.markdown(f'''
                                            <div class="post-container">
                                                <div style="display: flex; align-items: center; margin-bottom: 1rem;">
                                                    <img src="https://api.dicebear.com/7.x/initials/svg?seed=AI&backgroundColor=0A66C2" 
                                                         style="width: 48px; height: 48px; border-radius: 50%; margin-right: 1rem;" />
                                                    <div>
                                                        <div style="font-weight: bold;">AI Post Generator</div>
                                                        <div style="color: #888; font-size: 0.9rem;">Generated with {ai_provider_name}</div>
                                                    </div>
                                                </div>
                                                <div style="margin-bottom: 1rem;">
                                                    {formatted_post}
                                                </div>
                                            </div>
                                        ''', unsafe_allow_html=True)
                                        
                                        # # Copy button
                                        # post_js = post.replace('"', '\\"').replace('\n', '\\n')
                                        # st.markdown(f"""
                                        #     <button 
                                        #         class="copy-button"
                                        #         onclick="
                                        #             navigator.clipboard.writeText('{post_js}');
                                        #             this.innerHTML='✅ Copied!';
                                        #             setTimeout(() => this.innerHTML='📋 Copy to Clipboard', 2000);
                                        #         "
                                        #     >
                                        #         📋 Copy to Clipboard
                                        #     </button>
                                        # """, unsafe_allow_html=True)
                                    else:
                                        st.error(f"Failed to generate post with {ai_provider_name}. Please try again.")
                except:
                    st.error("Please enter a valid URL")
    
    with col2:
        st.markdown('<div class="stats-card">', unsafe_allow_html=True)
        st.markdown("### 📊 Statistics")
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("Posts Generated", st.session_state.posts_generated)
        with col_b:
            st.metric("Active Model", ai_provider_name)
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
