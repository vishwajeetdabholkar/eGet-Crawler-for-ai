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
import tempfile
import uuid
import os
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

class BrowserContext:
    """Enhanced browser context management with anti-detection and better logging"""
    def __init__(self, browser: webdriver.Chrome, config: Dict[str, Any]):
        logger.info("Initializing new browser context")
        self.cloudflare_handler = CloudflareHandler()
        self.browser = browser
        self.config = config
        self.original_window = browser.current_window_handle
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

            # Anti-detection measures
            self.browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    window.chrome = {
                        runtime: {}
                    };
                    
                    // Hide automation-related properties
                    const automationProperties = ['__webdriver_evaluate', '__selenium_evaluate',
                        '__webdriver_script_function', '__webdriver_script_func', '__webdriver_script_fn',
                        '__fxdriver_evaluate', '__driver_unwrapped', '__webdriver_unwrapped',
                        '__driver_evaluate', '__selenium_unwrapped', '__fxdriver_unwrapped'];
                    
                    automationProperties.forEach(prop => {
                        Object.defineProperty(document, prop, {
                            get: () => undefined,
                            set: () => undefined
                        });
                    });
                """
            })

            # Set realistic user agent and platform
            self.browser.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                "platform": "Windows"
            })

            stealth_js = """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    
                    window.chrome = {
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
                        },
                        runtime: {
                            OnInstalledReason: {
                                CHROME_UPDATE: 'chrome_update',
                                INSTALL: 'install',
                                SHARED_MODULE_UPDATE: 'shared_module_update',
                                UPDATE: 'update'
                            },
                            OnRestartRequiredReason: {
                                APP_UPDATE: 'app_update',
                                OS_UPDATE: 'os_update',
                                PERIODIC: 'periodic'
                            },
                            PlatformArch: {
                                ARM: 'arm',
                                ARM64: 'arm64',
                                MIPS: 'mips',
                                MIPS64: 'mips64',
                                X86_32: 'x86-32',
                                X86_64: 'x86-64'
                            },
                            PlatformNaclArch: {
                                ARM: 'arm',
                                MIPS: 'mips',
                                MIPS64: 'mips64',
                                X86_32: 'x86-32',
                                X86_64: 'x86-64'
                            },
                            PlatformOs: {
                                ANDROID: 'android',
                                CROS: 'cros',
                                LINUX: 'linux',
                                MAC: 'mac',
                                OPENBSD: 'openbsd',
                                WIN: 'win'
                            },
                            RequestUpdateCheckStatus: {
                                NO_UPDATE: 'no_update',
                                THROTTLED: 'throttled',
                                UPDATE_AVAILABLE: 'update_available'
                            }
                        }
                    };
                """
            self.browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': stealth_js
            })

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

    async def navigate(self, url: str, timeout: int = 30):
        """Enhanced navigation with Cloudflare handling"""
        logger.info(f"Navigating to URL: {url}")
        start_time = time.time()
        
        try:
            self.browser.set_page_load_timeout(timeout)
            self.browser.get(url)
            
            # Check for Cloudflare
            if await self.cloudflare_handler.is_cloudflare_challenge(self.browser):
                logger.info("Detected Cloudflare challenge, waiting for completion")
                challenge_complete = await self.cloudflare_handler.wait_for_challenge_completion(
                    self.browser,
                    timeout=timeout
                )
                if not challenge_complete:
                    raise Exception("Failed to bypass Cloudflare challenge")
            
            await self._wait_for_network_idle()
            logger.info(f"Navigation completed in {time.time() - start_time:.2f}s")
            
        except TimeoutException:
            logger.warning(f"Initial page load timeout for {url}, retrying with longer timeout")
            try:
                self.browser.execute_script("window.stop();")
                self.browser.set_page_load_timeout(timeout * 2)
                self.browser.get(url)
                
                # Check for Cloudflare again after retry
                if await self.cloudflare_handler.is_cloudflare_challenge(self.browser):
                    challenge_complete = await self.cloudflare_handler.wait_for_challenge_completion(
                        self.browser,
                        timeout=timeout
                    )
                    if not challenge_complete:
                        raise Exception("Failed to bypass Cloudflare challenge")
                        
                await self._wait_for_network_idle()
                logger.info(f"Navigation completed after retry in {time.time() - start_time:.2f}s")
            except Exception as e:
                logger.error(f"Navigation failed even after retry: {str(e)}")
                raise

    async def _wait_for_network_idle(self, idle_time: float = 1.0, timeout: float = 10.0):
        """Wait for network activity to settle with detailed logging"""
        logger.debug("Waiting for network to become idle")
        try:
            start_time = time.time()
            script = """
                return new Promise((resolve) => {
                    let lastCount = performance.getEntriesByType('resource').length;
                    let checkCount = 0;
                    const interval = setInterval(() => {
                        const currentCount = performance.getEntriesByType('resource').length;
                        if (currentCount === lastCount) {
                            checkCount++;
                            if (checkCount >= 3) {
                                clearInterval(interval);
                                resolve({
                                    resourceCount: currentCount,
                                    timeElapsed: performance.now()
                                });
                            }
                        } else {
                            checkCount = 0;
                            lastCount = currentCount;
                        }
                    }, 333);
                });
            """
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.browser.execute_script(script)
            )
            logger.debug(f"Network idle achieved. Resources loaded: {result.get('resourceCount', 'unknown')}")
            logger.debug(f"Network idle wait took {time.time() - start_time:.2f}s")
        except Exception as e:
            logger.warning(f"Error waiting for network idle: {str(e)}")

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
    """Enhanced browser pool management"""
    def __init__(self, max_browsers: int = 3):
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

    def _create_browser_options(self) -> Options:
        """Create optimized browser options"""
        options = Options()
        
        # Performance-focused options
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        
        # Memory optimization
        options.add_argument('--disable-javascript')
        options.add_argument('--blink-settings=imagesEnabled=false')
        options.add_argument('--js-flags=--max-old-space-size=512')
        
        # Network optimization
        options.add_argument('--disable-features=NetworkService')
        options.add_argument('--dns-prefetch-disable')
        
        # Additional stability options
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-infobars')
        
        # Set specific capabilities
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        
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
                    service = Service(ChromeDriverManager().install())
                    
                    try:
                        browser = webdriver.Chrome(service=service, options=options)
                        self.active_browsers.add(browser)
                        self.browser_metrics['created'] += 1
                        self.browser_metrics['current_active'] = len(self.active_browsers)
                        logger.info(f"Created new browser {id(browser)}")
                        return BrowserContext(browser, {
                            'window_width': 1280,
                            'window_height': 1024
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
    def __init__(self, max_concurrent: int = 5):
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
    async def create(cls, max_concurrent: int = 5, cache_service: Optional[CacheService] = None) -> 'WebScraper':
        """Factory method for creating WebScraper instance with optional cache service"""
        instance = cls(max_concurrent=max_concurrent)
        instance.cache_service = cache_service  # Set the cache service
        if instance.cache_service:
            await instance.cache_service.connect()
        return instance
    
    async def _get_page_content(self, url: str, options: Dict[str, Any]) -> Dict[str, Any]:
        context = await self.browser_pool.get_browser()
        try:
            await context.navigate(url, timeout=options.get('timeout', 30))
            
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

class CloudflareHandler:
    def __init__(self):
        self.cf_challenge_selectors = [
            "#challenge-form",
            "#challenge-running",
            "div[class*='cf-browser-verification']",
            "#cf-challenge-running"
        ]

    async def is_cloudflare_challenge(self, browser: webdriver.Chrome) -> bool:
        """Check if page has Cloudflare challenge"""
        try:
            # Check page title first
            title = browser.title.lower()
            if "just a moment" in title or "attention required" in title:
                logger.info("Detected Cloudflare challenge page by title")
                return True
                
            # Check for challenge elements
            for selector in self.cf_challenge_selectors:
                try:
                    if browser.find_element(By.CSS_SELECTOR, selector):
                        logger.info(f"Detected Cloudflare challenge element: {selector}")
                        return True
                except:
                    continue
                    
            # Check page source for common Cloudflare text
            page_source = browser.page_source.lower()
            cf_indicators = [
                "cloudflare",
                "ray id:",
                "please wait while we verify",
                "please enable cookies",
                "please complete the security check"
            ]
            
            for indicator in cf_indicators:
                if indicator in page_source:
                    logger.info(f"Detected Cloudflare challenge by text: {indicator}")
                    return True
                    
            return False
            
        except Exception as e:
            logger.error(f"Error checking Cloudflare challenge: {e}")
            return False
            
    async def solve_challenge(self, browser: webdriver.Chrome) -> bool:
        logger.info("Attempting to solve Cloudflare challenge")
        try:
            # Wait for iframe if it exists
            try:
                iframe = WebDriverWait(browser, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[title*='challenge']"))
                )
                browser.switch_to.frame(iframe)
            except:
                pass

            # Try to find and click the checkbox
            try:
                checkbox = WebDriverWait(browser, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='checkbox'], .checkbox"))
                )
                if checkbox.is_displayed():
                    checkbox.click()
                    logger.info("Clicked challenge checkbox")
            except:
                pass

            # Switch back to main content
            browser.switch_to.default_content()
            
            return True
        except Exception as e:
            logger.error(f"Error solving challenge: {e}")
            return False

    async def wait_for_challenge_completion(self, browser: webdriver.Chrome, timeout: int = 30) -> bool:
        """Modified to actively solve challenge"""
        logger.info("Waiting for Cloudflare challenge completion")
        start_time = time.time()
        solve_attempts = 0
        
        try:
            while time.time() - start_time < timeout:
                if not await self.is_cloudflare_challenge(browser):
                    logger.info("Cloudflare challenge completed")
                    return True
                
                # Attempt to solve every 5 seconds
                if solve_attempts < 3:  # Limit solve attempts
                    await self.solve_challenge(browser)
                    solve_attempts += 1
                    logger.info(f"Challenge solve attempt {solve_attempts}")
                
                await asyncio.sleep(2)
            
            logger.warning("Cloudflare challenge timeout")
            return False
            
        except Exception as e:
            logger.error(f"Error waiting for challenge completion: {e}")
            return False

