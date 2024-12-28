from datetime import timedelta
from typing import Dict, Any, List, Optional, Set
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
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
from core.exceptions import BrowserError
from core.config import get_settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from services.cache import cache_service
from services.cache.cache_service import CacheService
from services.extractors.structured_data import StructuredDataExtractor

# Metrics for monitoring
from prometheus_client import Counter, Histogram
SCRAPE_REQUESTS = Counter('scraper_requests_total', 'Total number of scrape requests')
SCRAPE_ERRORS = Counter('scraper_errors_total', 'Total number of scrape errors')
SCRAPE_DURATION = Histogram('scraper_duration_seconds', 'Time spent scraping URLs')

settings = get_settings()

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
        self.html2text_handler = html2text.HTML2Text()
        self.html2text_handler.ignore_links = False
        self.html2text_handler.ignore_images = False
        self.html2text_handler.ignore_tables = False
        self.html2text_handler.body_width = 0
    
    def _clean_html(self, html: str) -> str:
        """Clean HTML content with enhanced filtering"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove unwanted elements
            for element in soup.find_all([
                'script', 'style', 'iframe', 'nav', 'footer',
                'noscript', 'meta', 'link', 'comment'
            ]):
                element.decompose()
            
            # Clean attributes
            for tag in soup.find_all(True):
                allowed_attrs = ['href', 'src', 'alt', 'title']
                attrs = dict(tag.attrs)
                for attr in attrs:
                    if attr not in allowed_attrs:
                        del tag[attr]
            
            return str(soup)
        except Exception as e:
            logger.error(f"HTML cleaning failed: {str(e)}")
            raise
    
    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract comprehensive metadata from HTML"""
        metadata = {}
        
        # Get title with fallbacks
        title_tag = (
            soup.find('meta', property='og:title') or 
            soup.find('title')
        )
        if title_tag:
            metadata['title'] = title_tag.get('content', '') or title_tag.string
            
        # Get meta tags with prioritized mappings
        meta_mappings = {
            'description': ['description', 'og:description'],
            'language': ['language', 'og:locale'],
            'author': ['author', 'article:author'],
            'published_date': ['article:published_time', 'publishedDate'],
            'keywords': ['keywords'],
            'image': ['og:image']
        }
        
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            
            if name and content:
                for key, possible_names in meta_mappings.items():
                    if name.lower() in possible_names:
                        metadata[key] = content.strip()
        
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

    async def extract_content(self, html: str, only_main: bool = True) -> Dict[str, Any]:
        """Main content extraction method with error handling"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            metadata = self._extract_metadata(soup)
            
            if only_main:
                content = self._find_main_content(soup)
                if content:
                    html = content
            
            clean_html = self._clean_html(html)
            markdown = self.html2text_handler.handle(clean_html)
            
            return {
                'html': clean_html,
                'markdown': markdown,
                'metadata': metadata
            }
        except Exception as e:
            logger.error(f"Content extraction failed: {str(e)}")
            raise

class BrowserManager:
    """Manages browser instances with Selenium"""
    
    def __init__(self, max_browsers: int = 3):
        self.max_browsers = max_browsers
        self.browsers: List[webdriver.Chrome] = []
        self.lock = asyncio.Lock()
        self.active_browsers: Set[webdriver.Chrome] = set()

    async def _verify_browser(self, browser: webdriver.Chrome) -> bool:
        """Verify if browser is working properly"""
        try:
            browser.current_url
            return True
        except Exception:
            return False
    
    async def get_browser(self) -> webdriver.Chrome:
        """Get a browser instance with cross-platform compatibility"""
        async with self.lock:
            try:
                # Try to get an existing browser from pool
                while self.browsers:
                    browser = self.browsers.pop()
                    # Verify browser health
                    if await self._verify_browser(browser):
                        self.active_browsers.add(browser)
                        return browser
                    else:
                        # Clean up unhealthy browser
                        try:
                            browser.quit()
                        except Exception as e:
                            logger.warning(f"Failed to quit unhealthy browser: {str(e)}")

                # If no browser available, create new one
                logger.info("Starting new browser...")
                options = Options()

                # Common performance-focused options
                options.add_argument('--headless=new')
                options.add_argument('--disable-gpu')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-plugins')
                options.add_argument('--ignore-certificate-errors')
                options.add_argument('--window-size=1024,768')
                
                # Performance optimization options
                options.add_argument('--disable-features=VizDisplayCompositor')
                options.add_argument('--disable-features=UseSkiaRenderer')
                options.add_argument('--disable-gl-drawing-for-tests')
                options.add_argument('--disable-software-rasterizer')
                
                # Disable logging and notifications
                options.add_experimental_option('excludeSwitches', ['enable-logging'])
                options.add_argument('--disable-notifications')
                
                # Memory optimization
                options.add_argument('--disable-javascript')  # If JS isn't needed
                options.add_argument('--blink-settings=imagesEnabled=false')  # Disable images
                options.add_argument('--disable-canvas-aa')  # Disable canvas anti-aliasing
                options.add_argument('--disable-2d-canvas-clip-aa')  # Disable 2D canvas clip anti-aliasing
                
                # Platform-specific configurations
                if sys.platform.startswith('linux'):
                    # Linux-specific options
                    options.binary_location = "/usr/bin/google-chrome"
                    service = Service()  # Let webdriver_manager handle the path
                else:
                    # Windows/Mac options
                    service = Service(ChromeDriverManager().install())

                # Initialize browser
                browser = webdriver.Chrome(service=service, options=options)
                browser.set_window_size(1024, 768)  # Explicit window size
                
                # Set page load strategy to 'eager' for faster loading
                browser.execute_cdp_cmd('Page.setWebLifecycleState', {'state': 'active'})
                
                # Track the browser as active
                self.active_browsers.add(browser)
                
                return browser
                
            except Exception as e:
                logger.error(f"Failed to initialize browser: {str(e)}")
                raise BrowserError("initialization", str(e))

    async def release_browser(self, browser: webdriver.Chrome):
        """Release a browser back to the pool or close it"""
        if not browser:
            return
            
        async with self.lock:
            try:
                # Remove from active browsers tracking
                self.active_browsers.discard(browser)
                
                # Check if we should keep this browser
                if len(self.browsers) < self.max_browsers:
                    try:
                        # Verify browser is still healthy before reusing
                        if await self._verify_browser(browser):
                            # Clear browser state
                            try:
                                browser.delete_all_cookies()
                                browser.execute_script("window.localStorage.clear();")
                                browser.execute_script("window.sessionStorage.clear();")
                                # Navigate to blank page to clear current state
                                browser.get("about:blank")
                                
                                # Add to pool for reuse
                                self.browsers.append(browser)
                                logger.debug("Browser released back to pool")
                                return
                            except Exception as e:
                                logger.warning(f"Failed to clean browser state: {str(e)}")
                                # If cleanup fails, we'll close it below
                    except Exception as e:
                        logger.warning(f"Browser health check failed: {str(e)}")
                        # If verification fails, we'll close it below
                
                # If we reach here, we need to close the browser
                try:
                    browser.quit()
                    logger.debug("Browser closed successfully")
                except Exception as e:
                    logger.warning(f"Error while closing browser: {str(e)}")
                    # Even if quit fails, we've removed it from our tracking
                    
            except Exception as e:
                logger.error(f"Error in release_browser: {str(e)}")
                # Ensure browser is closed on error
                try:
                    browser.quit()
                except Exception as close_error:
                    logger.error(f"Failed to close browser in error handler: {str(close_error)}")

    def cleanup(self):
        """Clean up browser resources"""
        all_browsers = list(self.active_browsers) + self.browsers
        for browser in all_browsers:
            try:
                browser.quit()
            except Exception as e:
                logger.error(f"Error closing browser: {str(e)}")
        
        self.browsers.clear()
        self.active_browsers.clear()

class WebScraper:
    def __init__(self, max_concurrent: int = 5):
        # Core components initialization
        self.browser_manager = BrowserManager(max_browsers=max_concurrent)
        self.content_extractor = ContentExtractor()
        self.structured_data_extractor = StructuredDataExtractor()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.cache_service = None
        # Keep track of browsers in use
        self.active_browsers = set()
    
    @classmethod
    async def create(cls, max_concurrent: int = 5, cache_service: Optional[CacheService] = None) -> 'WebScraper':
        """Factory method for creating WebScraper instance with optional cache service"""
        instance = cls(max_concurrent=max_concurrent)
        instance.cache_service = cache_service  # Set the cache service
        if instance.cache_service:
            await instance.cache_service.connect()
        return instance
    
    async def _get_page_content(self, url: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Get page content with optimized browser management"""
        browser = await self.browser_manager.get_browser()
        self.active_browsers.add(browser)
        
        try:
            timeout = options.get('timeout', 30)
            browser.set_page_load_timeout(timeout)
            
            try:
                await asyncio.get_event_loop().run_in_executor(None, browser.get, url)
            except TimeoutException:
                logger.warning(f"Timeout loading {url}, retrying with longer timeout")
                browser.set_page_load_timeout(timeout * 2)
                await asyncio.get_event_loop().run_in_executor(None, browser.get, url)
            
            if options.get('wait_for_selector'):
                wait = WebDriverWait(browser, timeout)
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    wait.until,
                    EC.presence_of_element_located((By.CSS_SELECTOR, options['wait_for_selector']))
                )
            
            # Execute JavaScript
            script = """
                return {
                    content: document.documentElement.outerHTML,
                    links: Array.from(document.getElementsByTagName('a')).map(a => ({
                        href: a.href,
                        text: a.textContent.trim(),
                        rel: a.rel
                    }))
                }
            """
            
            # Run JavaScript execution and screenshot capture concurrently
            js_future = asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: browser.execute_script(script)
            )

            screenshot_future = None
            if options.get('include_screenshot'):
                screenshot_future = asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: base64.b64encode(browser.get_screenshot_as_png()).decode('utf-8')
                )
            
            # Wait for JavaScript result
            page_data = await js_future
            
            # Wait for screenshot if needed
            screenshot = None
            if screenshot_future:
                screenshot = await screenshot_future
            
            response = {
                'content': page_data['content'],
                'raw_content': page_data['content'] if options.get('include_raw_html') else None,
                'status': 200,
                'screenshot': screenshot,
                'links': page_data['links'],
                'headers': {}
            }
            
            # Schedule browser release
            asyncio.create_task(self._release_browser(browser))
            return response
            
        except Exception as e:
            # Ensure browser is released on error
            asyncio.create_task(self._release_browser(browser))
            raise e
    
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
        try:
            # Release all active browsers
            release_tasks = [
                self._release_browser(browser) 
                for browser in self.active_browsers.copy()
            ]
            await asyncio.gather(*release_tasks)
            
            # Final cleanup
            await self.browser_manager.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
