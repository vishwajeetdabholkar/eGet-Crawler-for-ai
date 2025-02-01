# Web Content Assistant: Interactive RAG Application Using eGet-CrawlerForAi

A production-grade web application that demonstrates the power of eGet Scraper API by providing an interactive, chat-based interface for querying and analyzing web content. This application showcases how eGet's advanced web scraping capabilities can be leveraged to build practical RAG (Retrieval-Augmented Generation) solutions.

## 🌟 Key Features

- **Smart Content Processing**: Extract and process content from any web page while maintaining context and structure
- **Flexible Model Selection**: Switch between different embedding and chat models (OpenAI/Ollama) seamlessly
- **Interactive Chat Interface**: Query processed content using natural language
- **Content Analytics**: Visualize content distribution and metadata
- **Persistent Storage**: Save and manage processed content and chat histories

## 🔧 Technical Architecture

- **Frontend**: Streamlit for interactive UI
- **Content Processing**: eGet Scraper API for web content extraction
- **Vector Storage**: ChromaDB for embedding storage and similarity search
- **Model Support**:
  - OpenAI's GPT models for chat completion
  - Ollama for local model inference
  - Choice of embedding models (OpenAI/Nomic)

## 💡 Business Value

1. **Knowledge Base Creation**
   - Quickly build searchable knowledge bases from web content
   - Maintain content structure and context for accurate retrieval
   - Support multiple content types (articles, documentation, research)

2. **Content Analysis**
   - Analyze content distribution across domains and types
   - Track content freshness and relevance
   - Monitor usage patterns and popular queries

3. **Cost Optimization**
   - Flexible model selection between cloud and local options
   - Efficient content chunking and retrieval
   - Caching and persistence to minimize reprocessing

4. **User Experience**
   - Natural language querying of web content
   - Context-aware responses with source attribution
   - Interactive content exploration

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- eGet Scraper API running locally (setup using `https://github.com/vishwajeetdabholkar/eGet-Crawler-for-ai/tree/main`)
- OpenAI API key (for OpenAI models)
- Ollama (for local models)

### Installation
```bash
# Clone the repository
git clone https://github.com/vishwajeetdabholkar/eGet-Crawler-for-ai/tree/main/
cd eGet-Crawler-for-ai/cookbook/web_content_assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY=your_api_key
```

### Running the Application
```bash
# Start eGet Scraper API (follow eGet documentation) : https://github.com/vishwajeetdabholkar/eGet-Crawler-for-ai/blob/main/readme.md#local-installation
# Start Ollama (if using local models)
ollama serve

# Run the application
streamlit run app.py
```

## 📖 How It Works

1. **Content Processing**
   - User submits a URL
   - eGet Scraper API extracts and processes the content
   - Content is chunked and stored with embeddings in ChromaDB

2. **Content Retrieval**
   - User enters a natural language query
   - System retrieves relevant content chunks using similarity search
   - LLM generates a response based on retrieved context

3. **Model Management**
   - Switch between different embedding and chat models
   - Mix and match models based on needs (e.g., Ollama embeddings with OpenAI chat)
   - All model changes are handled seamlessly

## 🎯 Use Cases

- **Documentation Analysis**: Quick access to technical documentation
- **Research Assistance**: Process and query research papers and articles
- **Content Exploration**: Interactive exploration of web content
- **Knowledge Management**: Build and maintain topic-specific knowledge bases

