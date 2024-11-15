from typing import Set, Optional, Dict
import asyncio
from collections import deque
from datetime import datetime
import time
from loguru import logger
from models.crawler_request import CrawlerRequest
from models.crawler_response import CrawlStatus
from asyncio import Queue

class QueueManager:
    """
    Manages the queue of URLs to be crawled with rate limiting and depth tracking.
    """
    
    def __init__(self, request: CrawlerRequest):
        """
        Initialize the queue manager.
        
        Args:
            request (CrawlerRequest): The crawler request containing settings
        """
        self.max_depth = request.max_depth
        self.max_pages = request.max_pages
        # self.queue: deque = deque()
        self.queue: Queue = Queue()
        self.seen_urls: Set[str] = set()
        self.in_progress: Set[str] = set()
        self.url_depths: Dict[str, int] = {}
        self.rate_limit_delay = 0.0  # seconds between requests
        self.last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def add_url(self, url: str, depth: int = 0, parent_url: Optional[str] = None) -> bool:
        """
        Add a URL to the queue if it hasn't been seen and respects depth limits.
        
        Args:
            url (str): URL to add
            depth (int): Depth of the URL in the crawl tree
            parent_url (Optional[str]): URL that led to this URL
            
        Returns:
            bool: True if URL was added, False if skipped
        """
        async with self._lock:
            if (url not in self.seen_urls and 
                depth <= self.max_depth and 
                len(self.seen_urls) < self.max_pages):
                
                # self.queue.append(url)
                self.seen_urls.add(url)
                self.url_depths[url] = depth
                await self.queue.put(url)
                logger.debug(f"Added URL to queue: {url} (depth: {depth})")
                return True
            return False

    async def get_next_url(self) -> Optional[str]:
        """
        Get the next URL to crawl, respecting rate limits.
        
        Returns:
            Optional[str]: Next URL to crawl or None if queue is empty
        """
        async with self._lock:
            # if not self.queue:
            #     return None
            if self.queue.empty():
                return None

            # Apply rate limiting
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - time_since_last)

            # url = self.queue.popleft()
            url = await self.queue.get()
            self.in_progress.add(url)
            self.last_request_time = time.time()
            
            return url

    async def mark_complete(self, url: str) -> None:
        """Mark a URL as completed"""
        async with self._lock:
            self.in_progress.discard(url)

    def get_depth(self, url: str) -> int:
        """Get the depth of a URL"""
        return self.url_depths.get(url, 0)

    @property
    def is_complete(self) -> bool:
        """Check if crawling is complete"""
        return not self.queue and not self.in_progress

    @property
    def stats(self) -> Dict:
        """Get current queue statistics"""
        return {
            "queued": len(self.queue),
            "in_progress": len(self.in_progress),
            "total_seen": len(self.seen_urls)
        }