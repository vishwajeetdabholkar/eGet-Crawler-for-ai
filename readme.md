# eGet - Advanced Web Scraping Framework

eGet is a high-performance, production-grade web scraping framework built with Python. It provides a robust API for extracting content from web pages with features like dynamic content handling, structured data extraction, and extensive customization options.

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
│   └── v1/
│       └── endpoints/     # API endpoint definitions
├── core/
│   ├── config.py         # Configuration management
│   └── exceptions.py     # Custom exception definitions
├── models/
│   ├── request.py        # Request models
│   └── response.py       # Response models
├── services/
│   ├── crawler/          # Web crawling services
│   ├── extractors/       # Content extraction services
│   └── scraper/          # Core scraping logic
└── main.py              # Application entry point
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
SECRET_KEY=your-secret-key-here
```

### 🐳 Docker Setup

1. Build the Docker image:
```bash
docker build -t eget-scraper .
```

2. Run with Docker Compose:
```bash
docker-compose up -d
```

This will start:
- eGet API service on port 8000
- Prometheus monitoring on port 9090

#### Docker Environment Variables

Configure the service through environment variables in `docker-compose.yml`:

```yaml
environment:
  - DEBUG=false
  - LOG_LEVEL=INFO
  - WORKERS=4
  - MAX_CONCURRENT_SCRAPES=5
  - TIMEOUT=30
  - SECRET_KEY=your-secret-key-here
```

## 📝 API Usage

### Basic Scraping Request

```python
import requests

url = "http://localhost:8000/api/v1/scrape"
payload = {
    "url": "https://example.com",
    "formats": ["markdown", "html"],
    "onlyMainContent": True,
    "includeScreenshot": False,
    "includeRawHtml": False
}

response = requests.post(url, json=payload)
print(response.json())
```

### Content Crawling

```python
url = "http://localhost:8000/api/v1/crawl"
payload = {
    "url": "https://example.com",
    "max_depth": 3,
    "max_pages": 100,
    "exclude_patterns": [r"\/api\/.*", r".*\.(jpg|jpeg|png|gif)$"],
    "include_patterns": [r"\/blog\/.*"],
    "respect_robots_txt": True
}

response = requests.post(url, json=payload)
print(response.json())
```

## 🔍 Monitoring

The API exposes Prometheus metrics at `/metrics` endpoint:

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
- [ ] Implement proxy support
- [ ] Add caching mechanism
- [ ] Support custom JavaScript injection
- [ ] Improve content extraction algorithms
- [ ] Add support for sitemap-based crawling
- [ ] Implement rate limiting per domain
- [ ] Add support for custom extraction rules

## 📄 License

This project is licensed under the Apache License - see the LICENSE file for details.

## 🙏 Acknowledgments

- FastAPI for the amazing web framework
- Selenium team for browser automation
- Beautiful Soup for HTML parsing
- All contributors who help improve this project

