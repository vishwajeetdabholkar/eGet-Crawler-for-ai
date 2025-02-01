# eGet - Advanced Web Scraping Framework for AI

eGet is a high-performance, production-grade web scraping framework built with Python. 
It provides a robust API for extracting content from web pages with features like dynamic content handling, structured data extraction, and extensive customization options.
eGet transforms complex websites into AI-ready content with a single API call, handling everything from JavaScript-rendered pages to dynamic content while delivering clean, structured markdown that's perfect for RAG applications. 
With its powerful crawling capabilities and intelligent content extraction, developers can effortlessly build comprehensive knowledge bases by turning any website into high-quality training data, making it an essential tool for teams building modern AI applications that need to understand and process web content at scale.

## 🚀 Features

- **Dynamic Content Handling**: 
  - Full JavaScript rendering support
  - Configurable wait conditions
  - Custom page interactions
  
- **Content Extraction**:
  - Smart main content detection
  - Markdown conversion
  - HTML cleaning and formatting
  - Structured data extraction (JSON-LD, OpenGraph, Twitter Cards)
  
- **Performance & Reliability**:
  - Browser resource pooling
  - Concurrent request handling
  - Rate limiting and retry mechanisms
  - Prometheus metrics integration
  
- **Additional Features**:
  - Screenshot capture
  - Metadata extraction
  - Link discovery
  - Robots.txt compliance
  - Configurable crawl depth and scope

## 🛠️ Technology Stack

- **FastAPI**: Modern, fast web framework for building APIs
- **Selenium**: Browser automation and JavaScript rendering
- **BeautifulSoup4**: HTML parsing and content extraction
- **Prometheus**: Metrics and monitoring
- **Tenacity**: Retry mechanisms and error handling

## 📦 Project Structure

```
eGet/
├── api/
│   ├── __init__.py
│   └── v1/
│       └── endpoints/
│           ├── crawler.py      # Crawler endpoint
│           ├── scraper.py      # Scraper endpoint
│           ├── chunker.py      # Semantic chunking endpoint
│           └── converter.py    # File conversion endpoint
├── core/
│   ├── __init__.py
│   ├── config.py              # Enhanced settings and configuration
│   ├── exceptions.py          # Extended custom exception classes
│   └── logging.py             # Logging configuration
├── models/
│   ├── __init__.py
│   ├── crawler_request.py     # Crawler request models
│   ├── crawler_response.py    # Crawler response models
│   ├── request.py             # Scraper request models
│   ├── response.py            # Scraper response models
│   ├── chunk_request.py       # Chunk request models
│   ├── chunk_response.py      # Chunk response models
│   └── file_conversion_models.py # File conversion models
├── services/
│   ├── cache/
│   │   ├── __init__.py
│   │   └── cache_service.py   # Enhanced cache implementation
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── crawler_service.py # Main crawler implementation
│   │   ├── link_extractor.py  # Enhanced URL extraction
│   │   └── queue_manager.py   # Advanced queue management
│   ├── chunker/
│   │   ├── __init__.py
│   │   ├── chunk_service.py   # Chunk service implementation
│   │   ├── semantic_chunker.py # Enhanced chunking implementation
│   │   └── markdown_parser.py  # Advanced markdown parsing
│   ├── converters/            # Document conversion services
|   |    ├── __init__.py
|   |    ├── base_converter.py          # Base converter abstract class
|   |    ├── document_structure.py      # Document structure management
|   |    ├── file_utils.py             # File handling utilities
|   |    ├── converter_factory.py      # Converter instantiation factory
|   |    ├── conversion_service.py     # Main conversion orchestrator
|   |    └── converters/               # Individual converter implementations
|   |        ├── __init__.py
|   |        ├── pdf_converter.py      # PDF conversion implementation
|   |        ├── docx_converter.py     # DOCX conversion implementation
|   |        └── xlsx_converter.py     # XLSX conversion implementation
│   ├── extractors/
│   │   ├── structured_data.py # Enhanced structured data extraction
│   │   └── validators.py      # Extended data validation
│   └── scraper/
│       ├── __init__.py
│       └── scraper.py         # Enhanced scraper implementation
├── .env.template              # Extended environment template
├── docker-compose.yml         # Base Docker composition
├── docker-compose.dev.yml     # Development Docker composition
├── docker-compose.prod.yml    # Production Docker composition
├── Dockerfile                 # Enhanced Docker build
├── main.py                    # Enhanced application entry
├── prometheus.yml            # Prometheus monitoring config
└── requirements.txt          # Updated Python dependencies
```

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- Chrome/Chromium browser
- Docker (optional)

### Local Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/eget.git
cd eget
```

2. Create and activate virtual environment:
```bash
# Create virtual environment
python -m venv venv

# Activate on Windows
.\venv\Scripts\activate

# Activate on Unix or MacOS
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Chrome WebDriver:
```bash
playwright install chromium
```

5. Create `.env` file:
```env
DEBUG=True
LOG_LEVEL=INFO
PORT=8000
WORKERS=1
```

### 🐳 Docker Setup

We provide two environments for running eGet:

1. Build the Docker image for Development Environment:
```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
```
    This will start:

    eGet API service on port 8000 (with hot-reload)
    Redis cache on port 6379
    Prometheus monitoring on port 9090

2. Build the Docker image for Production Environment:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
    This starts production services with:

    - Optimized resource limits
    - Proper restart policies
    - Security configurations
    - Redis cache
    - Prometheus monitoring

#### Docker Environment Variables

Configure the service through environment variables:

```yaml
environment:
  # API Settings
  - DEBUG=false
  - LOG_LEVEL=INFO
  - WORKERS=4
  - MAX_CONCURRENT_SCRAPES=5
  - TIMEOUT=30

  # Cache Settings
  - CACHE_ENABLED=true
  - CACHE_TTL=86400  # Cache duration in seconds (24 hours)
  - REDIS_URL=redis://redis:6379

  # Chrome Settings
  - PYTHONUNBUFFERED=1
  - CHROME_BIN=/usr/bin/google-chrome
```

## 📝 API Usage Examples

### Single Page Scraping

```python
import requests

def scrape_page():
    url = "http://localhost:8000/api/v1/scrape"
    
    # Configure scraping options
    payload = {
        "url": "https://example.com",
        "formats": ["markdown", "html"],
        "onlyMainContent": True,
        "includeScreenshot": False,
        "includeRawHtml": False,
        "waitFor": 2000,  # Wait for dynamic content
        "extract": {
            "custom_config": {
                "remove_ads": True,
                "extract_tables": True
            }
        }
    }

    response = requests.post(url, json=payload)
    result = response.json()
    
    if result["success"]:
        # Access extracted content
        markdown_content = result["data"]["markdown"]
        html_content = result["data"]["html"]
        metadata = result["data"]["metadata"]
        structured_data = result["data"]["structured_data"]
        
        print(f"Title: {metadata.get('title')}")
        print(f"Language: {metadata.get('language')}")
        print("\nContent Preview:")
        print(markdown_content[:500])
        
        # The extracted content is clean and ready for:
        # 1. Creating embeddings for vector search
        # 2. Feeding into LLMs as context
        # 3. Knowledge graph construction
        # 4. Document indexing
        
    return result

```

### Content Crawling for RAG

```python
import requests
from typing import List, Dict

def crawl_site_for_rag() -> List[Dict]:
    url = "http://localhost:8000/api/v1/crawl"
    
    # Configure crawling parameters
    payload = {
        "url": "https://example.com",
        "max_depth": 2,  # How deep to crawl
        "max_pages": 50,  # Maximum pages to process
        "exclude_patterns": [
            r"\/api\/.*",  # Skip API endpoints
            r".*\.(jpg|jpeg|png|gif)$",  # Skip image files
            r"\/tag\/.*",  # Skip tag pages
            r"\/author\/.*"  # Skip author pages
        ],
        "include_patterns": [
            r"\/blog\/.*",  # Focus on blog content
            r"\/docs\/.*"   # And documentation
        ],
        "respect_robots_txt": True
    }

    response = requests.post(url, json=payload)
    pages = response.json()
    
    # Process crawled pages for RAG
    processed_documents = []
    for page in pages:
        doc = {
            "url": page["url"],
            "content": page["markdown"],
            "metadata": {
                "title": page.get("structured_data", {}).get("metaData", {}).get("title"),
                "description": page.get("structured_data", {}).get("metaData", {}).get("description"),
                "language": page.get("structured_data", {}).get("metaData", {}).get("language")
            }
        }
        processed_documents.append(doc)
        
    return processed_documents

# Usage in RAG pipeline
documents = crawl_site_for_rag()
# Now you can:
# 1. Create embeddings for each document
# 2. Store in vector database
# 3. Use for retrieval in RAG applications
```

### Response Structure

The scraper returns clean, structured data ready for AI processing:

```python
{
    "success": True,
    "data": {
        "markdown": "# Main Title\n\nClean, processed content...",
        "html": "<div>Clean HTML content...</div>",
        "metadata": {
            "title": "Page Title",
            "description": "Page description",
            "language": "en",
            "sourceURL": "https://example.com",
            "statusCode": 200
        },
        "structured_data": {
            "jsonLd": [...],  # JSON-LD data
            "openGraph": {...},  # OpenGraph metadata
            "twitterCard": {...},  # Twitter Card data
            "metaData": {...}  # Additional metadata
        }
    }
}
```

## 🔍 Monitoring

The API exposes Prometheus metrics at `/metrics`:

- `scraper_requests_total`: Total scrape requests
- `scraper_errors_total`: Error count
- `scraper_duration_seconds`: Scraping duration

Access Prometheus dashboard at `http://localhost:9090`

## 🤝 Contributing

We welcome contributions! Here's how you can help:

### Development Setup

1. Fork the repository
2. Create your feature branch:
```bash
git checkout -b feature/AmazingFeature
```

3. Set up development environment:
```bash
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt
```

4. Install pre-commit hooks:
```bash
pre-commit install
```

### Development Guidelines

1. **Code Style**:
   - Follow PEP 8 guidelines
   - Use meaningful variable and function names
   - Include docstrings for all classes and functions
   - Add type hints where applicable

2. **Testing**:
   - Write unit tests for new features
   - Ensure all tests pass before submitting PR
   - Maintain or improve code coverage

3. **Error Handling**:
   - Use custom exception classes
   - Implement proper error logging
   - Return meaningful error messages

4. **Documentation**:
   - Update docstrings and comments
   - Update README if needed
   - Include example usage for new features

### Pull Request Process

1. Update the README.md with details of changes
2. Update the requirements.txt if needed
3. Make sure all tests pass
4. Create detailed PR description
5. Follow the PR template

### Commit Guidelines

- Use clear, descriptive commit messages
- Follow conventional commits format:
  ```
  feat: add new feature
  fix: resolve bug
  docs: update documentation
  test: add tests
  refactor: code improvements
  ```

## 🔍 Roadmap

- [ ] Add comprehensive test suite
- [ ] Implement proxy support with rotation capabilities
- [ ] Add response caching mechanism
- [ ] Enhance JavaScript injection capabilities with user-defined scripts
- [ ] Add support for sitemap-based crawling
- [ ] Enhance per-domain rate limiting
- [ ] Add cookie management and session handling
- [ ] Implement custom response processors
- [ ] Add support for headless browser alternatives
- [ ] Implement distributed crawling capabilities
- [ ] Add export capabilities to various formats
- [ ] Enhance error recovery and resumption mechanisms

## 📄 License

This project is licensed under the Apache License - see the LICENSE file for details.

## 🙏 Acknowledgments

- FastAPI for the amazing web framework
- Selenium team for browser automation
- Beautiful Soup for HTML parsing
