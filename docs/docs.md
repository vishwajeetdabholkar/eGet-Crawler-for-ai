# eRAG - Advanced Web Scraping Framework for AI

## Table of Contents
1. [Introduction](#introduction)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Installation](#installation)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Usage Examples](#usage-examples)
8. [Deployment](#deployment)
9. [Monitoring](#monitoring)
10. [Contributing](#contributing)

## Introduction

eRAG is a production-grade web scraping framework designed specifically for AI applications. It provides a robust API for extracting clean, structured content from web pages, with features tailored for Retrieval Augmented Generation (RAG) and other AI-driven use cases.

The framework excels at handling JavaScript-rendered pages, dynamic content, and complex web applications while delivering clean, structured markdown output that's perfect for RAG applications. With its intelligent content extraction and crawling capabilities, eRAG helps developers build comprehensive knowledge bases by efficiently transforming web content into high-quality training data.

## Features

### Core Capabilities
- **Dynamic Content Handling**
  - Full JavaScript rendering support
  - Configurable wait conditions for dynamic content
  - Custom page interaction support
  - Intelligent main content detection

- **Content Processing**
  - Smart main content detection and extraction
  - Markdown conversion with structure preservation
  - HTML cleaning and standardization
  - Structured data extraction (JSON-LD, OpenGraph, Twitter Cards)
  - Semantic chunking for optimal RAG processing

- **Performance & Reliability**
  - Browser resource pooling
  - Concurrent request handling
  - Redis-based caching
  - Rate limiting and retry mechanisms
  - Prometheus metrics integration

- **Crawling Capabilities**
  - Configurable crawl depth and scope
  - Pattern-based URL filtering
  - robots.txt compliance
  - Link discovery and validation
  - Distributed crawling support

### Additional Features
- Screenshot capture
- Comprehensive metadata extraction
- Custom JavaScript execution
- Proxy support
- Cookie and session handling
- Export capabilities

## Architecture

The project follows a modular architecture with clear separation of concerns:

```
eRAG/
├── api/                  # API endpoints
├── core/                # Core functionality
├── models/              # Data models
└── services/           # Business logic services
    ├── cache/          # Caching service
    ├── crawler/        # Crawling service
    ├── chunker/        # Content chunking
    ├── extractors/     # Data extractors
    └── scraper/        # Web scraping
```

### Key Components

1. **API Layer**
   - FastAPI-based REST API
   - Request validation
   - Error handling
   - Response formatting

2. **Core Services**
   - WebScraper: Main scraping engine
   - CrawlerService: Web crawling orchestration
   - ChunkService: Semantic content chunking
   - CacheService: Redis-based caching

3. **Support Services**
   - BrowserManager: Selenium browser pool
   - ContentExtractor: Content processing
   - StructuredDataExtractor: Metadata extraction
   - LinkExtractor: URL processing

## API Reference

### Endpoints

#### 1. Scraper Endpoint
```http
POST /api/v1/scrape
```

Request Body:
```json
{
  "url": "https://example.com",
  "formats": ["markdown", "html"],
  "onlyMainContent": true,
  "includeTags": ["article", "section"],
  "excludeTags": ["nav", "footer"],
  "waitFor": 2000,
  "includeRawHtml": false,
  "includeScreenshot": false
}
```

Response:
```json
{
  "success": true,
  "data": {
    "markdown": "# Title\n\nContent...",
    "html": "<div>Cleaned content...</div>",
    "metadata": {
      "title": "Page Title",
      "description": "Page description",
      "language": "en",
      "sourceURL": "https://example.com",
      "statusCode": 200
    },
    "structured_data": {
      "jsonLd": [...],
      "openGraph": {...},
      "twitterCard": {...},
      "metaData": {...}
    }
  }
}
```

#### 2. Crawler Endpoint
```http
POST /api/v1/crawl
```

Request Body:
```json
{
  "url": "https://example.com",
  "max_depth": 2,
  "max_pages": 50,
  "exclude_patterns": [
    "\\/api\\/.*",
    ".*\\.(jpg|jpeg|png|gif)$"
  ],
  "include_patterns": [
    "\\/blog\\/.*",
    "\\/docs\\/.*"
  ],
  "respect_robots_txt": true
}
```

Response:
```json
[
  {
    "url": "https://example.com/page1",
    "markdown": "Content in markdown...",
    "structured_data": {
      "jsonLd": [...],
      "openGraph": {...},
      "twitterCard": {...},
      "metaData": {...}
    }
  }
]
```

#### 3. Chunker Endpoint
```http
POST /api/v1/chunk
```

Request Body:
```json
{
  "url": "https://example.com",
  "max_chunk_size": 512,
  "min_chunk_size": 128
}
```

Response:
```json
{
  "success": true,
  "markdown": "Original markdown content...",
  "chunks": [
    {
      "id": "uuid",
      "content": "Chunk content...",
      "type": "paragraph",
      "hierarchy": {
        "parent_id": "parent-uuid",
        "level": 1,
        "path": ["root", "section1"]
      },
      "metadata": {
        "heading": "Section Heading",
        "word_count": 100,
        "position": 1,
        "type": "paragraph"
      }
    }
  ],
  "stats": {
    "total_chunks": 10,
    "avg_chunk_size": 256,
    "processing_time": 1.5
  }
}
```

## Configuration

### Environment Variables

```env
# API Configuration
DEBUG=false
LOG_LEVEL=INFO
PORT=8000
WORKERS=4

# Security
SECRET_KEY=your-secure-key-here
API_KEY=your-api-key-here

# Scraper Settings
MAX_CONCURRENT_SCRAPES=5
TIMEOUT=30
SCREENSHOT_QUALITY=80

# Redis Configuration
REDIS_URL=redis://redis:6379
CACHE_TTL=86400
CACHE_ENABLED=true

# Rate Limiting
RATE_LIMIT_ENABLED=false
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_PERIOD=3600

# Monitoring
PROMETHEUS_ENABLED=true
```

## Usage Examples

### Basic Scraping
```python
import requests

def scrape_page():
    url = "http://localhost:8000/api/v1/scrape"
    payload = {
        "url": "https://example.com",
        "formats": ["markdown", "html"],
        "onlyMainContent": True,
        "waitFor": 2000
    }
    
    response = requests.post(url, json=payload)
    result = response.json()
    
    if result["success"]:
        markdown_content = result["data"]["markdown"]
        metadata = result["data"]["metadata"]
        print(f"Title: {metadata['title']}")
        print(f"Content: {markdown_content[:500]}")
```

### Crawling with Filtering
```python
def crawl_site():
    url = "http://localhost:8000/api/v1/crawl"
    payload = {
        "url": "https://example.com",
        "max_depth": 2,
        "max_pages": 50,
        "exclude_patterns": [
            r"\/api\/.*",
            r".*\.(jpg|jpeg|png|gif)$"
        ],
        "include_patterns": [
            r"\/blog\/.*",
            r"\/docs\/.*"
        ]
    }
    
    response = requests.post(url, json=payload)
    pages = response.json()
    
    for page in pages:
        print(f"URL: {page['url']}")
        print(f"Content: {page['markdown'][:200]}")
```

### Semantic Chunking
```python
def chunk_content():
    url = "http://localhost:8000/api/v1/chunk"
    payload = {
        "url": "https://example.com",
        "max_chunk_size": 512,
        "min_chunk_size": 128
    }
    
    response = requests.post(url, json=payload)
    result = response.json()
    
    if result["success"]:
        for chunk in result["chunks"]:
            print(f"Chunk {chunk['metadata']['position']}:")
            print(f"Type: {chunk['type']}")
            print(f"Content: {chunk['content'][:200]}")
            print("-" * 80)
```

## Deployment

### Docker Deployment

1. Development Environment:
```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

2. Production Environment:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Resource Requirements

Minimum recommended specifications:
- CPU: 2 cores
- RAM: 4GB
- Storage: 20GB

### Security Considerations

1. API Security:
   - Use API key authentication
   - Enable rate limiting
   - Set up CORS properly
   - Use HTTPS in production

2. Browser Security:
   - Run in sandboxed mode
   - Disable unnecessary features
   - Regular security updates

## Monitoring

### Prometheus Metrics

Available metrics:
- `scraper_requests_total`: Total number of scrape requests
- `scraper_errors_total`: Number of scraping errors
- `scraper_duration_seconds`: Time spent scraping URLs

Access metrics at: `http://localhost:9090`

### Health Checks

Endpoint: `/health`
```json
{
  "status": "healthy",
  "timestamp": 1641116400
}
```

## Contributing

### Development Setup

1. Fork `https://github.com/vishwajeetdabholkar/eGet-Crawler-for-ai.git` and then clone the repository:
```bash
git clone https://github.com/yourusername/eGet-Crawler-for-ai.git
cd eGet-Crawler-for-ai
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Code Style
- Follow PEP 8 guidelines
- Use meaningful variable names
- Include docstrings for all functions
- Add type hints
- Write unit tests for new features

### Pull Request Process
1. Create feature branch
2. Add tests
3. Update documentation
4. Submit PR with detailed description

## License

This project is licensed under the Apache License - see the LICENSE file for details.