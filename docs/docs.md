# eGet - The Web Scraper API Documentation

## Overview

The Web Scraper API is a production-grade service that enables automated web page content extraction and processing. It uses Selenium with Chrome WebDriver for rendering JavaScript-heavy pages and provides advanced features like screenshots, dynamic content handling, and customizable extraction options.

## Base URL

```
http://localhost:8000
```

## Authentication

The API uses JWT (JSON Web Token) Bearer authentication.

### Headers

```
Authorization: Bearer <your_jwt_token>
```

## Endpoints

### Health Check

```http
GET /health
```

Returns the current health status of the API.

#### Response

```json
{
    "status": "healthy",
    "timestamp": 1699456789.123
}
```

### Root

```http
GET /
```

Returns basic API information and available endpoints.

#### Response

```json
{
    "name": "Web Scraper API",
    "version": "1.0.0",
    "description": "Production-grade web scraper API",
    "docs_url": "/docs",
    "health_check": "/health"
}
```

### Scrape URL

```http
POST /scrape
```

Scrapes the specified URL and returns processed content based on the provided options.

#### Request Body

| Field | Type | Description | Required | Default |
|-------|------|-------------|----------|---------|
| url | string | The URL to scrape (must be a valid HTTP/HTTPS URL) | Yes | - |
| formats | array[string] | Desired output formats | Yes | - |
| onlyMainContent | boolean | Extract only the main content area | No | true |
| includeTags | array[string] | HTML tags to include in extraction | No | null |
| excludeTags | array[string] | HTML tags to exclude from extraction | No | null |
| headers | object | Custom HTTP headers for the request | No | null |
| waitFor | integer | Time to wait for dynamic content (in milliseconds) | No | null |
| mobile | boolean | Emulate mobile device | No | false |
| skipTlsVerification | boolean | Skip TLS/SSL verification | No | false |
| timeout | integer | Request timeout in milliseconds | No | 30000 |
| extract | object | Custom extraction configuration | No | null |
| actions | array[object] | Custom actions to perform before extraction | No | null |
| location | object | Geolocation settings | No | null |

#### Example Request

```json
{
    "url": "https://example.com",
    "formats": ["html", "markdown"],
    "onlyMainContent": true,
    "headers": {
        "User-Agent": "Custom User Agent"
    },
    "waitFor": 5000,
    "timeout": 30000,
    "actions": [
        {
            "type": "wait",
            "milliseconds": 2000
        },
        {
            "type": "click",
            "selector": "#load-more"
        }
    ]
}
```

#### Response

```json
{
    "success": true,
    "data": {
        "markdown": "# Page Title\n\nExtracted content...",
        "html": "<div>Extracted HTML content...</div>",
        "rawHtml": "<html>Full page HTML...</html>",
        "screenshot": "base64_encoded_screenshot_data",
        "links": [
            {
                "href": "https://example.com/link1",
                "text": "Link Text",
                "rel": "nofollow"
            }
        ],
        "metadata": {
            "title": "Page Title",
            "description": "Page description",
            "language": "en",
            "sourceURL": "https://example.com",
            "statusCode": 200
        }
    }
}
```

#### Error Response

```json
{
    "success": false,
    "data": {
        "metadata": {
            "sourceURL": "https://example.com",
            "statusCode": 500,
            "error": "Error message description"
        }
    }
}
```

## Response Codes

| Code | Description |
|------|-------------|
| 200 | Successful scraping operation |
| 400 | Bad request (invalid parameters) |
| 401 | Unauthorized (invalid or missing token) |
| 422 | Validation error (invalid request body) |
| 429 | Too many requests |
| 500 | Internal server error |
| 504 | Gateway timeout |

## Features

### Screenshot Capture
The API automatically captures a screenshot of the rendered page, returned as a base64-encoded string in the response.

### Dynamic Content Handling
- Configurable wait times for JavaScript-rendered content
- Custom actions (click, wait, scroll) before content extraction
- Selector-based waiting for specific elements

### Content Processing
- Main content extraction
- HTML cleaning and formatting
- Markdown conversion
- Metadata extraction
- Link extraction
- Multiple output formats

### Performance & Reliability
- Concurrent scraping support
- Automatic retries with exponential backoff
- Configurable timeouts
- Browser resource management
- Prometheus metrics integration

## Metrics

The API exposes Prometheus metrics at `/metrics` endpoint:

- `scraper_requests_total`: Total number of scrape requests
- `scraper_errors_total`: Total number of scrape errors
- `scraper_duration_seconds`: Time spent scraping URLs

## Rate Limiting

The API implements concurrent request limiting through:
- Maximum concurrent scrapes: 5 (default)
- Maximum browser instances: 3 (default)

## Environment Configuration

The API can be configured through environment variables:

```env
DEBUG=False
PORT=8000
WORKERS=4
LOG_LEVEL=INFO
SECRET_KEY=your-secret-key-here
MAX_WORKERS=3
TIMEOUT=30000
MAX_RETRIES=3
CONCURRENT_SCRAPES=5
```

## Error Handling

The API implements comprehensive error handling:

### Validation Errors
```json
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Validation error occurred",
        "details": [
            {
                "loc": ["body", "url"],
                "msg": "invalid or missing URL scheme",
                "type": "value_error.url.scheme"
            }
        ]
    }
}
```

### Scraper Errors
```json
{
    "error": {
        "code": "SCRAPER_ERROR",
        "message": "Failed to scrape URL",
        "details": "Timeout while loading page"
    }
}
```

## Best Practices

1. **Timeouts**: Set appropriate timeouts based on the target website's performance
2. **Retries**: The API automatically retries failed requests, but consider implementing client-side retry logic for reliability
3. **Resource Management**: Monitor concurrent requests to avoid overwhelming target servers
4. **Error Handling**: Implement proper error handling in your client code
5. **Content Extraction**: Use `onlyMainContent: true` for cleaner results when possible

## SDK Examples

### Python

```python
import requests
import json

def scrape_url(url, token):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'url': url,
        'formats': ['markdown', 'html'],
        'onlyMainContent': True,
        'timeout': 30000
    }
    
    response = requests.post(
        'http://localhost:8000/scrape',
        headers=headers,
        json=payload
    )
    
    return response.json()
```

### JavaScript

```javascript
async function scrapeUrl(url, token) {
    const response = await fetch('http://localhost:8000/scrape', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            url: url,
            formats: ['markdown', 'html'],
            onlyMainContent: true,
            timeout: 30000
        })
    });
    
    return await response.json();
}
```