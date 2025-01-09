# RAG Chatbot with eGet 🌐

A simple example showing how to build a RAG (Retrieval Augmented Generation) chatbot using eGet for web scraping. This example demonstrates how easily you can create a powerful chatbot that can answer questions about any web content.

## Prerequisites

1. Install eGet first:
```bash
# Follow installation steps from:
https://github.com/vishwajeetdabholkar/eGet-Crawler-for-ai/blob/main/readme.md
```

2. Make sure eGet is running at `http://localhost:8000`

## Setup This Example

1. Install required packages:
```bash
pip install streamlit chromadb openai requests tqdm
```

2. Add your OpenAI API key in the code:
```python
# In app.py, replace:
OPENAI_API_KEY = "your-api-key-here"
```

3. Run the app:
```bash
streamlit run eget/cookbook/chatbot/app.py
```

## How It Works

1. Enter URLs into the chatbot
2. eGet scrapes the content
3. Content is stored in ChromaDB
4. Ask questions about the content
5. Get accurate, sourced answers!

## Why This Matters

This example shows how easy it is to:
- Use eGet for reliable web scraping
- Build a RAG system with minimal code
- Create chatbots that can learn from any web content
- Get factual, source-backed responses

The real power comes from combining eGet's scraping capabilities with RAG architecture - allowing you to create AI applications that can understand and discuss any web content accurately.

## Example Usage

```python
# Scrape and understand any web content
urls = [
    "https://docs.example.com",
    "https://blog.example.com/article"
]

# Ask questions about the content
"What are the key points from these articles?"
"Can you compare the information from both sources?"
```

That's it! A simple but powerful example of RAG with eGet. 🚀