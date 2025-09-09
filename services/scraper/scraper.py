from datetime import timedelta
from typing import Dict, Any, List, Optional, Set
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import html2text
from loguru import logger
import base64
import re, sys
import asyncio
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import time
import tempfile
import uuid
import os
import random
import json
from core.exceptions import BrowserError
from core.config import get_settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from services.cache import cache_service
from services.cache.cache_service import CacheService
from services.extractors.structured_data import StructuredDataExtractor

# Metrics for monitoring
from prometheus_client import Counter, Histogram, Gauge
SCRAPE_REQUESTS = Counter('scraper_requests_total', 'Total number of scrape requests')
SCRAPE_ERRORS = Counter('scraper_errors_total', 'Total number of scrape errors')
SCRAPE_DURATION = Histogram('scraper_duration_seconds', 'Time spent scraping URLs')

# Browser Pool Metrics
BROWSER_POOL_SIZE = Gauge('browser_pool_size', 'Current number of browsers in pool')
BROWSER_CREATION_TOTAL = Counter('browser_creation_total', 'Total number of browsers created')
BROWSER_REUSE_TOTAL = Counter('browser_reuse_total', 'Total number of times browsers were reused')
BROWSER_FAILURES = Counter('browser_failures_total', 'Total number of browser creation/initialization failures')
BROWSER_CLEANUP_TOTAL = Counter('browser_cleanup_total', 'Total number of browser cleanup operations')

# Browser Health Metrics
BROWSER_MEMORY_USAGE = Histogram('browser_memory_usage_bytes', 'Browser memory usage in bytes',
                                buckets=[100*1024*1024, 500*1024*1024, 1024*1024*1024])  # 100MB, 500MB, 1GB buckets
BROWSER_HEALTH_CHECK_DURATION = Histogram('browser_health_check_seconds', 'Time spent on browser health checks')

# Navigation Metrics
PAGE_LOAD_DURATION = Histogram('page_load_duration_seconds', 'Time taken for page loads')
NETWORK_IDLE_WAIT_DURATION = Histogram('network_idle_wait_seconds', 'Time spent waiting for network idle')

# Cloudflare Metrics
CLOUDFLARE_CHALLENGES = Counter('cloudflare_challenges_total', 'Number of Cloudflare challenges encountered')
CLOUDFLARE_BYPASS_SUCCESS = Counter('cloudflare_bypass_success_total', 'Successful Cloudflare challenge bypasses')
CLOUDFLARE_BYPASS_FAILURE = Counter('cloudflare_bypass_failure_total', 'Failed Cloudflare challenge bypasses')

settings = get_settings()

# Enhanced User Agent Pool for better bot detection evasion
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
    
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:119.0) Gecko/20100101 Firefox/119.0",
    
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
]

# Enhanced bot detection patterns
BOT_DETECTION_PATTERNS = {
    'cloudflare': [
        r'cloudflare',
        r'ray id:',
        r'please wait while we verify',
        r'please enable cookies',
        r'please complete the security check',
        r'checking your browser',
        r'just a moment',
        r'attention required',
        r'cf-browser-verification',
        r'cf-challenge-running'
    ],
    'datadome': [
        r'datadome',
        r'access denied',
        r'blocked by datadome',
        r'captcha.*datadome'
    ],
    'incapsula': [
        r'incapsula',
        r'incap_ses',
        r'visid_incap',
        r'blocked by incapsula'
    ],
    'akamai': [
        r'akamai',
        r'ak-bmsc',
        r'akamai.*bot.*manager'
    ],
    'generic_captcha': [
        r'captcha',
        r'recaptcha',
        r'hcaptcha',
        r'security check',
        r'verify.*human'
    ]
}

# Enhanced stealth JavaScript for better bot detection evasion
ENHANCED_STEALTH_JS = """
    // Remove webdriver property
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
    
    // Mock plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            {
                name: 'Chrome PDF Plugin',
                filename: 'internal-pdf-viewer',
                description: 'Portable Document Format'
            },
            {
                name: 'Chrome PDF Viewer',
                filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                description: ''
            },
            {
                name: 'Native Client',
                filename: 'internal-nacl-plugin',
                description: ''
            }
        ]
    });
    
    // Mock languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en']
    });
    
    // Mock permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
    
    // Mock chrome object
    window.chrome = {
        runtime: {
            onConnect: undefined,
            onMessage: undefined
        },
        app: {
            isInstalled: false,
            InstallState: {
                DISABLED: 'disabled',
                INSTALLED: 'installed',
                NOT_INSTALLED: 'not_installed'
            },
            RunningState: {
                CANNOT_RUN: 'cannot_run',
                READY_TO_RUN: 'ready_to_run',
                RUNNING: 'running'
            }
        }
    };
    
    // Hide automation indicators
    const automationProperties = [
        '__webdriver_evaluate', '__selenium_evaluate', '__webdriver_script_function',
        '__webdriver_script_func', '__webdriver_script_fn', '__fxdriver_evaluate',
        '__driver_unwrapped', '__webdriver_unwrapped', '__driver_evaluate',
        '__selenium_unwrapped', '__fxdriver_unwrapped', '__webdriver_script_args',
        '__webdriver_script_result', '__webdriver_script_error'
    ];
    
    automationProperties.forEach(prop => {
        Object.defineProperty(document, prop, {
            get: () => undefined,
            set: () => undefined
        });
    });
    
    // Mock screen properties
    Object.defineProperty(screen, 'availHeight', {
        get: () => 1040
    });
    Object.defineProperty(screen, 'availWidth', {
        get: () => 1920
    });
    Object.defineProperty(screen, 'colorDepth', {
        get: () => 24
    });
    Object.defineProperty(screen, 'height', {
        get: () => 1080
    });
    Object.defineProperty(screen, 'width', {
        get: () => 1920
    });
    
    // Mock timezone
    Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {
        value: function() {
            return { timeZone: 'America/New_York' };
        }
    });
    
    // Mock canvas fingerprinting
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type) {
        if (type === '2d') {
            const context = getContext.call(this, type);
            const originalFillText = context.fillText;
            context.fillText = function() {
                // Add slight randomization to canvas fingerprinting
                const args = Array.from(arguments);
                if (args.length >= 3) {
                    args[1] += Math.random() * 0.1;
                    args[2] += Math.random() * 0.1;
                }
                return originalFillText.apply(this, args);
            };
            return context;
        }
        return getContext.call(this, type);
    };
"""

def with_retry(max_retries: int = 3, delay: float = 1.0):
    """Decorator for retry logic"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(WebDriverException)
)
def safe_get_url(browser: webdriver.Chrome, url: str, timeout: int):
    """Safely get URL with retry mechanism"""
    browser.set_page_load_timeout(timeout)
    return browser.get(url)

class ContentExtractor:
    """Enhanced content extraction with better cleaning and extraction logic"""
    
    def __init__(self):
        # Optimized html2text configuration for top-class markdown output
        self.html2text_handler = html2text.HTML2Text()
        self.html2text_handler.ignore_links = False
        self.html2text_handler.ignore_images = False  # Keep images for proper markdown conversion
        self.html2text_handler.ignore_tables = False
        self.html2text_handler.body_width = 0  # No line wrapping to preserve structure
        self.html2text_handler.unicode_snob = True  # Better Unicode handling
        self.html2text_handler.escape_snob = False  # Don't escape to preserve structure
        self.html2text_handler.mark_code = True  # Mark code blocks properly
        self.html2text_handler.wrap_links = False  # Don't wrap links
        self.html2text_handler.wrap_list_items = False  # Don't wrap list items
        self.html2text_handler.emphasis_mark = '*'  # Use * for emphasis
        self.html2text_handler.strong_mark = '**'  # Use ** for strong
        self.html2text_handler.ignore_emphasis = False  # Keep emphasis
        self.html2text_handler.ignore_anchors = False  # Keep anchors
        
        # Pre-compile regex patterns for faster processing
        import re
        self._whitespace_pattern = re.compile(r'\s+')
        self._header_pattern = re.compile(r'(#{1,6})([^#\s])')
        self._list_pattern = re.compile(r'(\n\s*)-([^\s])')
        self._html_comment_pattern = re.compile(r'<!--.*?-->', re.DOTALL)
        self._code_block_pattern = re.compile(r'```(\w+)?\n(.*?)\n```', re.DOTALL)
        self._inline_code_pattern = re.compile(r'`([^`]+)`')
        self._excessive_newlines = re.compile(r'\n{3,}')
        self._trailing_spaces = re.compile(r'[ \t]+$', re.MULTILINE)
    
    def _clean_html(self, html: str) -> str:
        """Clean HTML content while preserving structure and formatting"""
        try:
            # Use lxml parser for better performance (faster than html.parser)
            # Fallback to html.parser if lxml is not available
            try:
                soup = BeautifulSoup(html, 'lxml')
            except Exception:
                logger.debug("lxml parser not available, falling back to html.parser")
                soup = BeautifulSoup(html, 'html.parser')
            
            # Remove unwanted elements but preserve structure
            unwanted_tags = ['script', 'style', 'iframe', 'noscript', 'comment']
            for element in soup.find_all(unwanted_tags):
                element.decompose()
            
            # Remove navigation and footer but keep main content structure
            for element in soup.find_all(['nav', 'footer', 'header']):
                # Only remove if they don't contain main content
                if not element.find(['main', 'article', 'section']):
                    element.decompose()
            
            # Clean attributes while preserving important structure attributes
            allowed_attrs = {
                'href', 'src', 'alt', 'title', 'class', 'id', 'data-*',
                'role', 'aria-*', 'type', 'rel', 'target'
            }
            for tag in soup.find_all(True):
                if tag.attrs:
                    # Create new attrs dict with only allowed attributes
                    new_attrs = {}
                    for attr, value in tag.attrs.items():
                        if (attr in allowed_attrs or 
                            attr.startswith('data-') or 
                            attr.startswith('aria-')):
                            new_attrs[attr] = value
                    tag.attrs = new_attrs
            
            return str(soup)
        except Exception as e:
            logger.error(f"HTML cleaning failed: {str(e)}")
            raise
    
    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract comprehensive metadata from HTML matching expected output format"""
        metadata = {}
        
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text().strip()
        
        # Extract meta description
        desc_tag = soup.find('meta', attrs={'name': 'description'})
        if desc_tag:
            metadata['description'] = desc_tag.get('content', '').strip()
        
        # Extract Open Graph data with proper naming
        og_tags = soup.find_all('meta', attrs={'property': lambda x: x and x.startswith('og:')})
        for tag in og_tags:
            prop = tag.get('property', '').replace('og:', '')
            content = tag.get('content', '').strip()
            if prop and content:
                # Map to expected field names
                if prop == 'title':
                    metadata['ogTitle'] = content
                elif prop == 'description':
                    metadata['ogDescription'] = content
                elif prop == 'image':
                    metadata['ogImage'] = content
                elif prop == 'url':
                    metadata['ogUrl'] = content
                elif prop == 'site_name':
                    metadata['ogSiteName'] = content
                elif prop == 'type':
                    metadata['og:type'] = content
                elif prop == 'locale':
                    metadata['ogLocale'] = content
                else:
                    metadata[f'og{prop.capitalize()}'] = content
        
        # Extract Twitter Card data with proper naming
        twitter_tags = soup.find_all('meta', attrs={'name': lambda x: x and x.startswith('twitter:')})
        for tag in twitter_tags:
            name = tag.get('name', '').replace('twitter:', '')
            content = tag.get('content', '').strip()
            if name and content:
                metadata[f'twitter:{name}'] = content
        
        # Extract canonical URL
        canonical = soup.find('link', attrs={'rel': 'canonical'})
        if canonical:
            metadata['canonical_url'] = canonical.get('href', '').strip()
        
        # Extract favicon
        favicon = soup.find('link', attrs={'rel': 'icon'}) or soup.find('link', attrs={'rel': 'shortcut icon'})
        if favicon:
            metadata['favicon'] = favicon.get('href', '').strip()
        
        # Extract additional metadata fields
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        if viewport:
            metadata['viewport'] = viewport.get('content', '').strip()
        
        # Extract language
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            metadata['language'] = html_tag.get('lang')
        
        # Extract charset
        charset_tag = soup.find('meta', attrs={'charset': True})
        if charset_tag:
            metadata['charset'] = charset_tag.get('charset', '').strip()
        
        # Extract content type
        content_type = soup.find('meta', attrs={'http-equiv': 'content-type'})
        if content_type:
            metadata['contentType'] = content_type.get('content', '').strip()
        
        # Extract author information
        author_tag = soup.find('meta', attrs={'name': 'author'})
        if author_tag:
            metadata['authors'] = author_tag.get('content', '').strip()
        
        # Extract summary
        summary_tag = soup.find('meta', attrs={'name': 'summary'})
        if summary_tag:
            metadata['summary'] = summary_tag.get('content', '').strip()
        
        # Extract additional fields to match expected output
        # Extract published date from various sources
        pub_date = (soup.find('meta', attrs={'property': 'article:published_time'}) or
                   soup.find('meta', attrs={'name': 'article:published_time'}) or
                   soup.find('time', attrs={'datetime': True}))
        if pub_date:
            if pub_date.get('content'):
                metadata['published_at'] = pub_date.get('content', '').strip()
            elif pub_date.get('datetime'):
                metadata['published_at'] = pub_date.get('datetime', '').strip()
        
        # Extract categories/sections
        category = (soup.find('meta', attrs={'property': 'article:section'}) or
                   soup.find('meta', attrs={'name': 'article:section'}) or
                   soup.find('meta', attrs={'property': 'article:tag'}))
        if category:
            metadata['categories'] = category.get('content', '').strip()
        
        # Extract site ID
        site_id = soup.find('meta', attrs={'name': 'site-id'})
        if site_id:
            metadata['site-id'] = site_id.get('content', '').strip()
        
        # Extract app version
        app_version = soup.find('meta', attrs={'name': 'app-version'})
        if app_version:
            metadata['app-version'] = app_version.get('content', '').strip()
        
        # Extract author images
        author_img = soup.find('img', attrs={'alt': re.compile(r'author|writer', re.I)})
        if author_img:
            metadata['author_images'] = author_img.get('src', '').strip()
        
        # Extract docs boost
        docs_boost = soup.find('meta', attrs={'name': 'docs-boost'})
        if docs_boost:
            metadata['docs-boost'] = docs_boost.get('content', '').strip()
        
        # Extract FB app ID
        fb_app_id = soup.find('meta', attrs={'property': 'fb:app_id'})
        if fb_app_id:
            metadata['fb:app_id'] = fb_app_id.get('content', '').strip()
        
        return metadata

    def _find_main_content(self, soup: BeautifulSoup) -> Optional[str]:
        """Enhanced main content detection"""
        content_patterns = [
            {'tag': 'main'},
            {'tag': 'article'},
            {'tag': 'div', 'id': re.compile(r'content|main|article', re.I)},
            {'tag': 'div', 'class': re.compile(r'content|main|article', re.I)},
            {'tag': 'div', 'role': 'main'}
        ]
        
        for pattern in content_patterns:
            element = soup.find(**pattern)
            if element:
                return str(element)
        
        # Fallback: Find largest text container
        containers = soup.find_all(['div', 'section'])
        if containers:
            return str(max(containers, key=lambda x: len(x.get_text())))
        
        return None

    def _convert_to_markdown_with_images(self, html: str) -> str:
        """Convert HTML to markdown with enhanced image handling and structure preservation"""
        try:
            # Parse HTML to extract and enhance images
            try:
                soup = BeautifulSoup(html, 'lxml')
            except Exception:
                soup = BeautifulSoup(html, 'html.parser')
            
            # Enhance image tags for better markdown conversion
            for img in soup.find_all('img'):
                # Ensure alt text exists
                if not img.get('alt'):
                    img['alt'] = 'Image'
                
                # Add title if src exists but no title
                if img.get('src') and not img.get('title'):
                    # Extract filename from src for title
                    src = img.get('src', '')
                    if src:
                        filename = src.split('/')[-1].split('?')[0]  # Remove query params
                        img['title'] = filename
            
            # Convert to markdown using optimized html2text
            markdown = self.html2text_handler.handle(str(soup))
            
            # Post-process markdown for better structure preservation
            markdown = self._post_process_markdown(markdown)
            
            return markdown
            
        except Exception as e:
            logger.error(f"Markdown conversion failed: {str(e)}")
            # Fallback to basic conversion
            return self.html2text_handler.handle(html)

    def _post_process_markdown(self, markdown: str) -> str:
        """Post-process markdown to achieve top-class formatting matching expected output"""
        try:
            # Remove HTML comments using pre-compiled pattern
            markdown = self._html_comment_pattern.sub('', markdown)
            
            # Remove non-breaking spaces and other special characters
            markdown = markdown.replace('&nbsp;', ' ')
            markdown = markdown.replace('\xa0', ' ')
            markdown = markdown.replace('\u00a0', ' ')
            
            # Fix malformed headers using pre-compiled pattern
            markdown = self._header_pattern.sub(r'\1 \2', markdown)
            
            # Fix broken list formatting using pre-compiled pattern
            markdown = self._list_pattern.sub(r'\1- \2', markdown)
            
            # Clean up trailing spaces from each line
            markdown = self._trailing_spaces.sub('', markdown)
            
            # Process lines to improve formatting
            lines = markdown.split('\n')
            processed_lines = []
            in_code_block = False
            in_list = False
            
            for i, line in enumerate(lines):
                line = line.rstrip()
                
                # Handle code blocks
                if line.startswith('```'):
                    in_code_block = not in_code_block
                    processed_lines.append(line)
                    continue
                
                if in_code_block:
                    processed_lines.append(line)
                    continue
                
                # Handle empty lines
                if not line.strip():
                    # Only add empty line if previous line wasn't empty
                    if processed_lines and processed_lines[-1].strip():
                        processed_lines.append('')
                    continue
                
                # Handle headers
                if line.startswith('#'):
                    # Add spacing before header (except at start)
                    if processed_lines and processed_lines[-1].strip():
                        processed_lines.append('')
                    processed_lines.append(line)
                    # Add spacing after header
                    processed_lines.append('')
                    in_list = False
                    continue
                
                # Handle lists
                if line.strip().startswith(('-', '*', '+')) or re.match(r'^\s*\d+\.', line):
                    if not in_list and processed_lines and processed_lines[-1].strip():
                        processed_lines.append('')
                    processed_lines.append(line)
                    in_list = True
                    continue
                else:
                    in_list = False
                
                # Handle images
                if line.strip().startswith('!['):
                    if processed_lines and processed_lines[-1].strip():
                        processed_lines.append('')
                    processed_lines.append(line)
                    processed_lines.append('')
                    continue
                
                # Handle regular content
                processed_lines.append(line)
            
            markdown = '\n'.join(processed_lines)
            
            # Clean up excessive newlines (more than 2 consecutive)
            markdown = self._excessive_newlines.sub('\n\n', markdown)
            
            # Remove lines with only whitespace and single characters
            markdown = re.sub(r'^\s*[\*\.\-]\s*$', '', markdown, flags=re.MULTILINE)
            
            # Clean up any remaining excessive newlines after removing single character lines
            markdown = self._excessive_newlines.sub('\n\n', markdown)
            
            # Fix code block formatting - convert **Copy\n[code] to proper markdown triple backticks
            # Handle the exact format we see: **Copy\n[code]\n    content\n[/code]
            markdown = re.sub(r'\*\*Copy\n\[code\]', 'Copy\n\n```', markdown)
            markdown = re.sub(r'\[/code\]', '```', markdown)
            
            # Clean up any remaining [code] or [/code] tags that might be standalone
            markdown = re.sub(r'\[code\]', '```', markdown)
            markdown = re.sub(r'\[/code\]', '```', markdown)
            
            # Final cleanup - remove any remaining problematic lines and excessive spacing
            markdown = re.sub(r'^\s*[\*\.\-]\s*$', '', markdown, flags=re.MULTILINE)
            markdown = self._excessive_newlines.sub('\n\n', markdown)
            
            # Ensure proper spacing around code blocks
            markdown = re.sub(r'(\n*)(```[\w]*\n.*?\n```)(\n*)', r'\n\n\2\n\n', markdown, flags=re.DOTALL)
            
            # Ensure proper spacing around images
            markdown = re.sub(r'(\n*)(!\[.*?\]\(.*?\))(\n*)', r'\n\n\2\n\n', markdown)
            
            # Clean up any remaining excessive newlines
            markdown = self._excessive_newlines.sub('\n\n', markdown)
            
            # Final cleanup before returning - remove lines with only asterisks and double empty lines
            markdown = re.sub(r'^\s*\*\s*$', '', markdown, flags=re.MULTILINE)
            markdown = re.sub(r'\n{3,}', '\n\n', markdown)
            
            return markdown.strip()
            
        except Exception as e:
            logger.error(f"Markdown post-processing failed: {str(e)}")
            return markdown

    async def extract_content(self, html: str, only_main: bool = True) -> Dict[str, Any]:
        """Main content extraction method with optimized parsing and image handling"""
        try:
            # Use optimized parser (lxml if available, fallback to html.parser)
            try:
                soup = BeautifulSoup(html, 'lxml')
            except Exception:
                logger.debug("lxml parser not available, using html.parser")
                soup = BeautifulSoup(html, 'html.parser')
            
            # Extract metadata first
            metadata = self._extract_metadata(soup)
            
            # Find main content if requested
            if only_main:
                content = self._find_main_content(soup)
                if content:
                    # Re-parse the main content for cleaning
                    try:
                        soup = BeautifulSoup(str(content), 'lxml')
                    except Exception:
                        soup = BeautifulSoup(str(content), 'html.parser')
            
            # Clean HTML with optimized method
            clean_html = self._clean_html(str(soup))
            
            # Convert to markdown with enhanced image handling
            markdown = self._convert_to_markdown_with_images(clean_html)
            
            return {
                'html': clean_html,
                'markdown': markdown,
                'metadata': metadata
            }
        except Exception as e:
            logger.error(f"Content extraction failed: {str(e)}")
            raise

class BrowserContext:
    """Enhanced browser context management with anti-detection and better logging"""
    def __init__(self, browser: webdriver.Chrome, config: Dict[str, Any]):
        logger.info("Initializing new browser context")
        # Use the enhanced bot detection handler
        self.bot_detection_handler = EnhancedBotDetectionHandler()
        # Keep backward compatibility
        self.cloudflare_handler = self.bot_detection_handler
        self.browser = browser
        self.config = config
        self.original_window = browser.current_window_handle
        # Random user agent for this session
        self.user_agent = random.choice(USER_AGENTS)
        self._setup_browser()

    def _setup_browser(self):
        """Configure browser settings with anti-detection"""
        logger.debug("Setting up browser configurations")
        try:
            # Basic window setup
            self.browser.set_window_size(
                self.config.get('window_width', 1280),
                self.config.get('window_height', 1024)
            )
            
            # Apply performance optimizations
            self.browser.execute_cdp_cmd('Network.enable', {})
            self.browser.execute_cdp_cmd('Network.setBypassServiceWorker', {'bypass': True})
            self.browser.execute_cdp_cmd('Page.enable', {})

            # Enhanced anti-detection measures using the new stealth script
            self.browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                "source": ENHANCED_STEALTH_JS
            })

            # Set random user agent and platform based on the user agent
            platform = self._get_platform_from_user_agent(self.user_agent)
            self.browser.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": self.user_agent,
                "platform": platform
            })
            logger.info(f"Set user agent: {self.user_agent[:50]}...")
            logger.info(f"Set platform: {platform}")

            # Add stealth mode headers
            self.browser.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                "headers": {
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "accept-language": "en-US,en;q=0.9",
                    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                    "sec-fetch-user": "?1",
                    "upgrade-insecure-requests": "1",
                    "cf-ipcountry": "US",
                    "cf-connecting-ip": "127.0.0.1",
                    "cf-ray": "",  # Cloudflare ray ID
                    "cf-visitor": '{"scheme":"https"}',
                    "cache-control": "no-cache",
                    "pragma": "no-cache",
                }
            })

            logger.info("Browser setup completed successfully")
        except Exception as e:
            logger.error(f"Failed to setup browser: {str(e)}")
            raise

    def _get_platform_from_user_agent(self, user_agent: str) -> str:
        """Extract platform from user agent string"""
        user_agent_lower = user_agent.lower()
        if 'windows' in user_agent_lower:
            return 'Windows'
        elif 'macintosh' in user_agent_lower or 'mac os x' in user_agent_lower:
            return 'Mac'
        elif 'linux' in user_agent_lower:
            return 'Linux'
        elif 'android' in user_agent_lower:
            return 'Android'
        elif 'iphone' in user_agent_lower or 'ipad' in user_agent_lower:
            return 'iOS'
        else:
            return 'Windows'  # Default fallback

    async def navigate(self, url: str, timeout: int = 10):  # Reduced default timeout
        """Ultra-fast navigation optimized for speed"""
        logger.info(f"Fast navigation to URL: {url}")
        start_time = time.time()
        
        try:
            # Set aggressive page load timeout for speed
            self.browser.set_page_load_timeout(timeout)
            
            # Use eager loading strategy for faster page loads
            self.browser.execute_cdp_cmd('Page.setLifecycleEventsEnabled', {'enabled': True})
            
            # Navigate with minimal wait
            self.browser.get(url)
            
            # Check for bot protection systems
            bot_detection = await self.bot_detection_handler.detect_bot_protection(self.browser)
            if bot_detection['detected']:
                logger.info(f"Detected {bot_detection['type']} protection with confidence {bot_detection['confidence']}")
                CLOUDFLARE_CHALLENGES.inc()
                challenge_complete = await self.bot_detection_handler.wait_for_challenge_completion(
                    self.browser,
                    timeout=timeout
                )
                if not challenge_complete:
                    raise Exception(f"Failed to bypass {bot_detection['type']} challenge")
            
            await self._wait_for_network_idle()
            logger.info(f"Navigation completed in {time.time() - start_time:.2f}s")
            
        except TimeoutException:
            logger.warning(f"Initial page load timeout for {url}, retrying with longer timeout")
            try:
                self.browser.execute_script("window.stop();")
                self.browser.set_page_load_timeout(timeout * 2)
                self.browser.get(url)
                
                # Check for bot protection again after retry
                bot_detection = await self.bot_detection_handler.detect_bot_protection(self.browser)
                if bot_detection['detected']:
                    logger.info(f"Detected {bot_detection['type']} protection after retry")
                    CLOUDFLARE_CHALLENGES.inc()
                    challenge_complete = await self.bot_detection_handler.wait_for_challenge_completion(
                        self.browser,
                        timeout=timeout
                    )
                    if not challenge_complete:
                        raise Exception(f"Failed to bypass {bot_detection['type']} challenge")
                        
                await self._wait_for_network_idle()
                logger.info(f"Navigation completed after retry in {time.time() - start_time:.2f}s")
            except Exception as e:
                logger.error(f"Navigation failed even after retry: {str(e)}")
                raise

    async def _wait_for_network_idle(self, idle_time: float = 0.1, timeout: float = 2.0):
        """Ultra-fast network idle wait optimized for speed"""
        logger.debug("Fast network idle check")
        try:
            start_time = time.time()
            
            # Simple DOM ready check instead of complex network monitoring
            script = """
                return new Promise((resolve) => {
                    if (document.readyState === 'complete') {
                        resolve({ready: true, timeElapsed: 0});
                    } else {
                        const start = performance.now();
                        const checkReady = () => {
                            if (document.readyState === 'complete' || 
                                document.readyState === 'interactive') {
                                resolve({ready: true, timeElapsed: performance.now() - start});
                            } else {
                                setTimeout(checkReady, 50); // Check every 50ms
                            }
                        };
                        checkReady();
                    }
                });
            """
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.browser.execute_script(script)
            )
            
            elapsed = time.time() - start_time
            logger.debug(f"DOM ready in {elapsed:.3f}s")
            
            # Minimal additional wait for any remaining resources
            if elapsed < 0.5:  # If DOM loaded quickly, wait a bit more
                await asyncio.sleep(0.2)
            
        except Exception as e:
            logger.warning(f"Error in fast network check: {str(e)}")
            # Fallback: just wait a minimal time
            await asyncio.sleep(0.3)

    async def get_page_source(self) -> str:
        """Get page source with retry mechanism and logging"""
        logger.debug("Attempting to get page source")
        for attempt in range(3):
            try:
                source = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.browser.page_source
                )
                logger.debug(f"Page source retrieved successfully, size: {len(source)} bytes")
                return source
            except StaleElementReferenceException:
                logger.warning(f"Stale element on attempt {attempt + 1}, retrying...")
                if attempt == 2:
                    logger.error("Failed to get page source after all retries")
                    raise
                await asyncio.sleep(0.5)

    async def take_screenshot(self) -> str:
        """Take screenshot with enhanced error handling and logging"""
        logger.debug("Attempting to take screenshot")
        try:
            screenshot = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.browser.get_screenshot_as_png()
            )
            encoded = base64.b64encode(screenshot).decode('utf-8')
            logger.debug(f"Screenshot captured successfully, size: {len(encoded)} bytes")
            return encoded
        except Exception as e:
            logger.error(f"Screenshot failed: {str(e)}")
            return None

    async def cleanup(self):
        """Clean up browser resources with logging"""
        logger.debug("Starting browser context cleanup")
        try:
            self.browser.delete_all_cookies()
            logger.debug("Cookies cleared")
            
            self.browser.execute_script("window.localStorage.clear();")
            self.browser.execute_script("window.sessionStorage.clear();")
            logger.debug("Storage cleared")
            
            self.browser.get("about:blank")
            logger.debug("Navigated to blank page")
            
            logger.info("Browser context cleanup completed successfully")
        except Exception as e:
            logger.warning(f"Cleanup error: {str(e)}")

class BrowserPool:
    """Ultra-fast browser pool management optimized for speed"""
    def __init__(self, max_browsers: int = 10):  # Increased pool size
        self.max_browsers = max_browsers
        self.available_browsers: List[webdriver.Chrome] = []
        self.active_browsers: Set[webdriver.Chrome] = set()
        self.lock = asyncio.Lock()
        self.browser_metrics = {
            'created': 0,
            'reused': 0,
            'failed': 0,
            'current_active': 0
        }
        # Cache ChromeDriver service for faster browser creation
        self._cached_service = None

    def _create_browser_options(self) -> Options:
        """Create balanced browser options for speed while maintaining structure"""
        options = Options()
        
        # Core performance options
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        
        # Network and loading optimizations
        options.add_argument('--disable-background-networking')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-features=TranslateUI')
        options.add_argument('--disable-ipc-flooding-protection')
        options.add_argument('--disable-hang-monitor')
        options.add_argument('--disable-prompt-on-repost')
        options.add_argument('--disable-domain-reliability')
        options.add_argument('--disable-component-extensions-with-background-pages')
        
        # Memory and CPU optimizations
        options.add_argument('--memory-pressure-off')
        options.add_argument('--max_old_space_size=4096')
        options.add_argument('--js-flags=--max-old-space-size=4096')
        options.add_argument('--disable-background-mode')
        options.add_argument('--disable-low-res-tiling')
        
        # Balanced loading strategy - keep structure but optimize speed
        options.add_argument('--page-load-strategy=normal')  # Wait for DOM but not all resources
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        
        # Window size for proper rendering
        options.add_argument('--window-size=1280,720')
        
        # Minimal logging
        options.add_argument('--log-level=3')
        options.add_argument('--silent')
        
        # Balanced prefs - allow JS and CSS for structure, but optimize images
        prefs = {
            "profile.default_content_setting_values": {
                "notifications": 2,
                "geolocation": 2,
                "media_stream": 2,
                "images": 1,  # Allow images but optimize loading
                "plugins": 2,  # Block plugins
                "popups": 2,  # Block popups
                "javascript": 1  # Allow JavaScript for proper structure
            },
            "profile.managed_default_content_settings": {
                "images": 1  # Allow images
            },
            "profile.default_content_settings": {
                "images": 1  # Allow images
            }
        }
        options.add_experimental_option("prefs", prefs)
        
        return options

    async def get_browser(self) -> BrowserContext:
        """Get a browser with context and metrics tracking"""
        logger.info("Requesting browser from pool")
        async with self.lock:
            try:
                # Try to reuse an existing browser
                while self.available_browsers:
                    browser = self.available_browsers.pop()
                    logger.debug(f"Testing available browser {id(browser)}")
                    
                    if await self._is_browser_healthy(browser):
                        self.active_browsers.add(browser)
                        self.browser_metrics['reused'] += 1
                        self.browser_metrics['current_active'] = len(self.active_browsers)
                        logger.info(f"Reusing existing browser {id(browser)}")
                        return BrowserContext(browser, {
                            'window_width': 1280,
                            'window_height': 1024
                        })
                    else:
                        logger.warning(f"Unhealthy browser {id(browser)} found, cleaning up")
                        await self._safely_quit_browser(browser)

                # Create new browser if under limit
                if len(self.active_browsers) < self.max_browsers:
                    logger.info("Creating new browser instance")
                    options = self._create_browser_options()
                    
                    # Use cached service for faster browser creation
                    if not self._cached_service:
                        logger.info("Initializing cached ChromeDriver service")
                        self._cached_service = Service(ChromeDriverManager().install())
                    
                    try:
                        browser = webdriver.Chrome(service=self._cached_service, options=options)
                        self.active_browsers.add(browser)
                        self.browser_metrics['created'] += 1
                        self.browser_metrics['current_active'] = len(self.active_browsers)
                        logger.info(f"Created new browser {id(browser)}")
                        return BrowserContext(browser, {
                            'window_width': 1280,
                            'window_height': 720  # Match optimized window size
                        })
                    except Exception as e:
                        self.browser_metrics['failed'] += 1
                        logger.error(f"Failed to create browser: {str(e)}")
                        raise
                else:
                    logger.error(f"Max browsers ({self.max_browsers}) reached")
                    raise BrowserError("Too many active browsers")

            except Exception as e:
                logger.error(f"Browser pool error: {str(e)}")
                raise

    async def _is_browser_healthy(self, browser: webdriver.Chrome) -> bool:
        """Enhanced browser health check"""
        try:
            logger.debug(f"Checking health of browser {id(browser)}")
            start_time = time.time()
            
            # Basic connectivity check
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: browser.current_url
            )
            
            # Memory check (example threshold: 1GB)
            try:
                memory_info = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: browser.execute_script('return window.performance.memory.usedJSHeapSize')
                )
                if memory_info > 1024 * 1024 * 1024:  # 1GB
                    logger.warning(f"Browser {id(browser)} memory usage too high")
                    return False
            except:
                pass  # Memory check is optional
                
            logger.debug(f"Browser {id(browser)} health check completed in {time.time() - start_time:.2f}s")
            return True
            
        except Exception as e:
            logger.warning(f"Browser {id(browser)} health check failed: {str(e)}")
            return False

    async def release_browser(self, context: BrowserContext):
        """Release browser with enhanced error handling"""
        if not context:
            return

        async with self.lock:
            browser = context.browser
            browser_id = id(browser)
            logger.info(f"Releasing browser {browser_id}")
            
            try:
                await context.cleanup()
                
                if browser in self.active_browsers:
                    self.active_browsers.remove(browser)
                    self.browser_metrics['current_active'] = len(self.active_browsers)
                    
                    # Only reuse browser if pool not full and browser healthy
                    if len(self.available_browsers) < self.max_browsers:
                        if await self._is_browser_healthy(browser):
                            self.available_browsers.append(browser)
                            logger.info(f"Browser {browser_id} returned to pool")
                            return
                
                logger.info(f"Closing browser {browser_id}")
                await self._safely_quit_browser(browser)
                
            except Exception as e:
                logger.error(f"Error releasing browser {browser_id}: {str(e)}")
                await self._safely_quit_browser(browser)

    async def _safely_quit_browser(self, browser: webdriver.Chrome):
        """Safely quit browser with cleanup verification"""
        browser_id = id(browser)
        logger.debug(f"Quitting browser {browser_id}")
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                browser.quit
            )
            logger.info(f"Browser {browser_id} quit successfully")
        except Exception as e:
            logger.warning(f"Error quitting browser {browser_id}: {str(e)}")

    async def cleanup(self):
        """Comprehensive cleanup of all browser resources"""
        async with self.lock:
            logger.info("Starting browser pool cleanup")
            all_browsers = list(self.active_browsers) + self.available_browsers
            logger.info(f"Cleaning up {len(all_browsers)} browsers")
            
            quit_tasks = [self._safely_quit_browser(browser) for browser in all_browsers]
            await asyncio.gather(*quit_tasks, return_exceptions=True)
            
            self.available_browsers.clear()
            self.active_browsers.clear()
            self.browser_metrics['current_active'] = 0
            
            logger.info("Browser pool cleanup completed")

class WebScraper:
    def __init__(self, max_concurrent: int = 10):  # Increased concurrency
        # Core components initialization
        # self.browser_manager = BrowserManager(max_browsers=max_concurrent)
        self.browser_pool = BrowserPool(max_browsers=max_concurrent)
        self.content_extractor = ContentExtractor()
        self.structured_data_extractor = StructuredDataExtractor()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.cache_service = None
        # Keep track of browsers in use
        self.active_browsers = set()
    
    @classmethod
    async def create(cls, max_concurrent: int = 10, cache_service: Optional[CacheService] = None) -> 'WebScraper':
        """Factory method for creating WebScraper instance with optional cache service"""
        instance = cls(max_concurrent=max_concurrent)
        instance.cache_service = cache_service  # Set the cache service
        if instance.cache_service:
            await instance.cache_service.connect()
        return instance
    
    async def _get_page_content(self, url: str, options: Dict[str, Any]) -> Dict[str, Any]:
        context = await self.browser_pool.get_browser()
        try:
            # Use faster timeout for speed
            await context.navigate(url, timeout=options.get('timeout', 10))
            
            if options.get('wait_for_selector'):
                element_present = EC.presence_of_element_located(
                    (By.CSS_SELECTOR, options['wait_for_selector'])
                )
                WebDriverWait(context.browser, options.get('timeout', 30)).until(element_present)

            page_source = await context.get_page_source()
            
            screenshot = None
            if options.get('include_screenshot'):
                screenshot = await context.take_screenshot()

            links = context.browser.execute_script("""
                return Array.from(document.getElementsByTagName('a')).map(a => ({
                    href: a.href,
                    text: a.textContent.trim(),
                    rel: a.rel
                }));
            """)

            return {
                'content': page_source,
                'raw_content': page_source if options.get('include_raw_html') else None,
                'status': 200,
                'screenshot': screenshot,
                'links': links,
                'headers': {}
            }

        finally:
            await self.browser_pool.release_browser(context)

    async def _release_browser(self, browser: webdriver.Chrome):
        """Separate browser release method"""
        if browser in self.active_browsers:
            self.active_browsers.remove(browser)
            await self.browser_manager.release_browser(browser)
 
    async def scrape(self, url: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Main scraping method with caching"""
        SCRAPE_REQUESTS.inc()
        
        try:
            # Check cache first if caching is enabled
            if self.cache_service and not options.get('bypass_cache'):
                cached_result = await self.cache_service.get_cached_result(url, options)
                if cached_result:
                    return {
                        'success': True,
                        'data': cached_result,
                        'cached': True
                    }
            
            # If not cached or cache bypassed, proceed with scraping
            async with self.semaphore:
                try:
                    with SCRAPE_DURATION.time():
                        # Get and process page content
                        page_data = await self._get_page_content(url, options)
                        processed_data = await self._process_page_data(page_data, options, url)
                        
                        # Cache the result if caching is enabled
                        if self.cache_service and not options.get('bypass_cache'):
                            cache_ttl = options.get('cache_ttl', getattr(settings, 'CACHE_TTL', 86400))  # Default to 24 hours
                            await self.cache_service.cache_result(
                                url, 
                                options, 
                                processed_data,
                                ttl=timedelta(seconds=cache_ttl)
                            )
                        
                        return {
                            'success': True,
                            'data': processed_data,
                            'cached': False
                        }
                        
                except Exception as e:
                    SCRAPE_ERRORS.inc()
                    logger.error(f"Scraping error for {url}: {str(e)}")
                    return {
                        'success': False,
                        'data': {
                            'markdown': None,
                            'html': None,
                            'rawHtml': None,
                            'screenshot': None,
                            'links': None,
                            'actions': None,
                            'metadata': {
                                'title': None,
                                'description': None,
                                'language': None,
                                'sourceURL': url,
                                'statusCode': 500,
                                'error': str(e)
                            },
                            'llm_extraction': None,
                            'warning': str(e),
                            'structured_data': None
                        }
                    }
                    
        except Exception as e:
            logger.error(f"Unexpected error in scrape method: {str(e)}")
            SCRAPE_ERRORS.inc()
            raise

    async def _process_page_data(self, page_data: Dict[str, Any], 
                               options: Dict[str, Any], url: str) -> Dict[str, Any]:
        """Process page data with proper async handling"""
        try:
            # Create content extraction tasks
            content_task = self.content_extractor.extract_content(
                page_data['content'],
                options.get('only_main', True)
            )

            structured_data_future = asyncio.get_event_loop().run_in_executor(
                None,
                self.structured_data_extractor.extract_all,
                page_data['content']
            )

            # Wait for both tasks to complete
            processed_content, structured_data = await asyncio.gather(
                content_task,
                structured_data_future
            )

            # Build response data (rest remains the same)
            metadata = {
                'title': None,
                'description': None,
                'language': None,
                'sourceURL': url,
                'statusCode': page_data['status'],
                'error': None
            }
            if processed_content.get('metadata'):
                metadata.update(processed_content['metadata'])

            formatted_links = [
                link['href'] for link in page_data.get('links', [])
                if link.get('href')
            ] if page_data.get('links') else None

            return {
                'markdown': processed_content['markdown'],
                'html': processed_content['html'],
                'rawHtml': page_data['raw_content'],
                'screenshot': None,
                'links': formatted_links,
                'actions': ({'screenshots': [page_data['screenshot']]} 
                          if page_data.get('screenshot') else None),
                'metadata': metadata,
                'llm_extraction': None,
                'warning': None,
                'structured_data': structured_data
            }

        except Exception as e:
            logger.error(f"Data processing error: {str(e)}")
            raise
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.browser_pool.cleanup()

class EnhancedBotDetectionHandler:
    """Enhanced bot detection and challenge handling for multiple protection systems"""
    
    def __init__(self):
        # Cloudflare-specific selectors
        self.cf_challenge_selectors = [
            "#challenge-form",
            "#challenge-running", 
            "div[class*='cf-browser-verification']",
            "#cf-challenge-running",
            ".cf-browser-verification",
            "#cf-challenge-stage",
            ".cf-checking-browser",
            ".cf-wrapper"
        ]
        
        # Generic challenge selectors
        self.generic_challenge_selectors = [
            "[class*='captcha']",
            "[class*='challenge']",
            "[class*='verification']",
            "[class*='security-check']",
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            ".g-recaptcha",
            ".h-captcha"
        ]
        
        # DataDome selectors
        self.datadome_selectors = [
            "[class*='datadome']",
            "[id*='datadome']",
            ".dd-challenge"
        ]
        
        # Incapsula selectors
        self.incapsula_selectors = [
            "[class*='incap']",
            "[id*='incap']",
            ".incap-challenge"
        ]

    async def detect_bot_protection(self, browser: webdriver.Chrome) -> Dict[str, Any]:
        """Comprehensive bot protection detection"""
        detection_result = {
            'detected': False,
            'type': None,
            'confidence': 0,
            'selectors_found': [],
            'text_indicators': [],
            'page_title': None
        }
        
        try:
            # Get page title and source
            title = browser.title.lower()
            page_source = browser.page_source.lower()
            detection_result['page_title'] = title
            
            # Check for each protection system
            protection_systems = [
                ('cloudflare', self.cf_challenge_selectors, BOT_DETECTION_PATTERNS['cloudflare']),
                ('datadome', self.datadome_selectors, BOT_DETECTION_PATTERNS['datadome']),
                ('incapsula', self.incapsula_selectors, BOT_DETECTION_PATTERNS['incapsula']),
                ('akamai', [], BOT_DETECTION_PATTERNS['akamai']),
                ('generic_captcha', self.generic_challenge_selectors, BOT_DETECTION_PATTERNS['generic_captcha'])
            ]
            
            max_confidence = 0
            detected_type = None
            
            for system_name, selectors, patterns in protection_systems:
                confidence = 0
                found_selectors = []
                found_text = []
                
                # Check selectors
                for selector in selectors:
                    try:
                        if browser.find_element(By.CSS_SELECTOR, selector):
                            found_selectors.append(selector)
                            confidence += 20
                    except:
                        continue
                
                # Check text patterns
                for pattern in patterns:
                    if re.search(pattern, page_source, re.IGNORECASE):
                        found_text.append(pattern)
                        confidence += 15
                
                # Check title patterns
                if system_name == 'cloudflare':
                    if any(phrase in title for phrase in ['just a moment', 'attention required', 'checking your browser']):
                        confidence += 25
                        found_text.append('title_indicator')
                
                if confidence > max_confidence:
                    max_confidence = confidence
                    detected_type = system_name
                    detection_result['selectors_found'] = found_selectors
                    detection_result['text_indicators'] = found_text
            
            if max_confidence > 30:  # Threshold for detection
                detection_result['detected'] = True
                detection_result['type'] = detected_type
                detection_result['confidence'] = max_confidence
                logger.info(f"Detected {detected_type} protection with confidence {max_confidence}")
            
            return detection_result
            
        except Exception as e:
            logger.error(f"Error in bot protection detection: {e}")
            return detection_result

    async def is_cloudflare_challenge(self, browser: webdriver.Chrome) -> bool:
        """Check if page has Cloudflare challenge (backward compatibility)"""
        detection = await self.detect_bot_protection(browser)
        return detection['detected'] and detection['type'] == 'cloudflare'
            
    async def solve_cloudflare_challenge(self, browser: webdriver.Chrome) -> bool:
        """Enhanced Cloudflare challenge solving with multiple strategies"""
        logger.info("Attempting to solve Cloudflare challenge")
        try:
            # Strategy 1: Handle iframe-based challenges
            try:
                iframe_selectors = [
                    "iframe[title*='challenge']",
                    "iframe[src*='challenge']",
                    "iframe[src*='cloudflare']",
                    "iframe[src*='cf-challenge']"
                ]
                
                for iframe_selector in iframe_selectors:
                    try:
                        iframe = WebDriverWait(browser, 3).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, iframe_selector))
                        )
                        browser.switch_to.frame(iframe)
                        logger.info(f"Switched to iframe: {iframe_selector}")
                        
                        # Look for checkbox in iframe
                        checkbox_selectors = [
                            "input[type='checkbox']",
                            ".checkbox",
                            "[class*='checkbox']",
                            "#challenge-form input",
                            ".cf-turnstile"
                        ]
                        
                        for checkbox_selector in checkbox_selectors:
                            try:
                                checkbox = WebDriverWait(browser, 2).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, checkbox_selector))
                                )
                                if checkbox.is_displayed():
                                    # Human-like delay before clicking
                                    await asyncio.sleep(random.uniform(0.5, 1.5))
                                    checkbox.click()
                                    logger.info(f"Clicked challenge checkbox: {checkbox_selector}")
                                    break
                            except:
                                continue
                        
                        browser.switch_to.default_content()
                        break
                    except:
                        continue
            except:
                pass

            # Strategy 2: Handle direct page challenges
            checkbox_selectors = [
                "input[type='checkbox']",
                ".checkbox",
                "[class*='checkbox']",
                "#challenge-form input",
                ".cf-turnstile",
                "[data-ray]",
                ".cf-challenge-running input"
            ]
            
            for checkbox_selector in checkbox_selectors:
                try:
                    checkbox = WebDriverWait(browser, 2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, checkbox_selector))
                    )
                    if checkbox.is_displayed():
                        # Human-like delay before clicking
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        checkbox.click()
                        logger.info(f"Clicked direct challenge checkbox: {checkbox_selector}")
                        break
                except:
                    continue

            # Strategy 3: Handle Turnstile challenges
            try:
                turnstile_elements = browser.find_elements(By.CSS_SELECTOR, ".cf-turnstile, [data-sitekey]")
                if turnstile_elements:
                    logger.info("Detected Turnstile challenge - waiting for automatic completion")
                    # Turnstile usually completes automatically, just wait
                    await asyncio.sleep(3)
            except:
                pass

            # Strategy 4: Simulate human behavior
            try:
                # Random mouse movements and scrolling
                browser.execute_script("window.scrollTo(0, Math.random() * 100);")
                await asyncio.sleep(random.uniform(0.5, 1.0))
                browser.execute_script("window.scrollTo(0, 0);")
            except:
                pass
            
            return True
            
        except Exception as e:
            logger.error(f"Error solving Cloudflare challenge: {e}")
            return False

    async def solve_generic_captcha(self, browser: webdriver.Chrome) -> bool:
        """Handle generic captcha challenges"""
        logger.info("Attempting to solve generic captcha challenge")
        try:
            # Look for reCAPTCHA
            recaptcha_selectors = [
                ".g-recaptcha",
                "iframe[src*='recaptcha']",
                "[data-sitekey]"
            ]
            
            for selector in recaptcha_selectors:
                try:
                    element = browser.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed():
                        logger.info("Detected reCAPTCHA - waiting for manual completion")
                        # For reCAPTCHA, we typically need to wait for manual intervention
                        # or use a solving service
                        await asyncio.sleep(5)
                        return True
                except:
                    continue
            
            # Look for hCaptcha
            hcaptcha_selectors = [
                ".h-captcha",
                "iframe[src*='hcaptcha']"
            ]
            
            for selector in hcaptcha_selectors:
                try:
                    element = browser.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed():
                        logger.info("Detected hCaptcha - waiting for manual completion")
                        await asyncio.sleep(5)
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error solving generic captcha: {e}")
            return False

    async def solve_challenge(self, browser: webdriver.Chrome, challenge_type: str = None) -> bool:
        """Generic challenge solving method that routes to specific handlers"""
        if not challenge_type:
            detection = await self.detect_bot_protection(browser)
            challenge_type = detection.get('type', 'cloudflare')
        
        logger.info(f"Attempting to solve {challenge_type} challenge")
        
        if challenge_type == 'cloudflare':
            return await self.solve_cloudflare_challenge(browser)
        elif challenge_type in ['generic_captcha', 'recaptcha', 'hcaptcha']:
            return await self.solve_generic_captcha(browser)
        else:
            # For other protection systems, try generic approach
            logger.info(f"No specific handler for {challenge_type}, trying generic approach")
            return await self.solve_cloudflare_challenge(browser)

    async def wait_for_challenge_completion(self, browser: webdriver.Chrome, timeout: int = 30) -> bool:
        """Enhanced challenge completion waiting with better detection"""
        logger.info("Waiting for challenge completion")
        start_time = time.time()
        solve_attempts = 0
        last_detection = None
        
        try:
            while time.time() - start_time < timeout:
                # Check if challenge is still present
                detection = await self.detect_bot_protection(browser)
                
                if not detection['detected']:
                    logger.info("Challenge completed successfully")
                    CLOUDFLARE_BYPASS_SUCCESS.inc()
                    return True
                
                # If challenge type changed, update our approach
                if last_detection and last_detection.get('type') != detection.get('type'):
                    logger.info(f"Challenge type changed from {last_detection.get('type')} to {detection.get('type')}")
                    solve_attempts = 0  # Reset attempts for new challenge type
                
                last_detection = detection
                
                # Attempt to solve challenge
                if solve_attempts < 5:  # Increased max attempts
                    success = await self.solve_challenge(browser, detection.get('type'))
                    solve_attempts += 1
                    logger.info(f"Challenge solve attempt {solve_attempts} for {detection.get('type')}")
                    
                    if success:
                        # Wait a bit after solving attempt
                        await asyncio.sleep(random.uniform(2, 4))
                
                # Progressive wait times
                wait_time = min(2 + (solve_attempts * 0.5), 5)
                await asyncio.sleep(wait_time)
            
            logger.warning(f"Challenge timeout after {timeout}s")
            CLOUDFLARE_BYPASS_FAILURE.inc()
            return False
            
        except Exception as e:
            logger.error(f"Error waiting for challenge completion: {e}")
            CLOUDFLARE_BYPASS_FAILURE.inc()
            return False

# Backward compatibility - keep the old CloudflareHandler class
class CloudflareHandler(EnhancedBotDetectionHandler):
    """Backward compatibility wrapper for the old CloudflareHandler"""
    
    def __init__(self):
        super().__init__()
        # Keep the old selectors for backward compatibility
        self.cf_challenge_selectors = [
            "#challenge-form",
            "#challenge-running",
            "div[class*='cf-browser-verification']",
            "#cf-challenge-running"
        ]

