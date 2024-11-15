from typing import Dict, List, Optional, Set
import asyncio
import uuid
from datetime import datetime
from loguru import logger
from concurrent.futures import ThreadPoolExecutor

from services.scraper.scraper import WebScraper
from .link_extractor import LinkExtractor
from .queue_manager import QueueManager
from models.crawler_request import CrawlerRequest
from models.crawler_response import (
    CrawlerResponse, CrawlStatus, CrawlStats, 
    CrawledPage, CrawlStatus
)
from core.exceptions import ScraperException

class CrawlerService:
    """
    Production-grade crawler service that orchestrates web crawling.
    """
    
    def __init__(self, max_concurrent: int = 5, worker_threads: int = 3):
        self.max_concurrent = max_concurrent
        self.worker_threads = worker_threads
        self.scraper = WebScraper(max_concurrent=max_concurrent)
        self.active_crawls: Dict[uuid.UUID, CrawlerResponse] = {}
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=worker_threads)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_page(self, url: str, depth: int, 
                          queue_manager: QueueManager,
                          link_extractor: LinkExtractor, 
                          response: CrawlerResponse,
                          request: CrawlerRequest) -> None:
        """Process a single page"""
        try:
            logger.debug(f"Processing {url} at depth {depth}")
            
            scrape_result = await self.scraper.scrape(
                url,
                {
                    "only_main": True,
                    "include_raw_html": False,
                    "include_screenshot": False
                }
            )
            
            if scrape_result["success"]:
                # Create page result
                page = CrawledPage(
                    url=url,
                    markdown=scrape_result["data"]["markdown"],
                    structured_data=scrape_result["data"].get("structured_data"),
                    scrape_id=uuid.uuid4(),
                    depth=depth,
                )
                
                # Extract new links if within depth limit
                if depth < request.max_depth:
                    new_links = link_extractor.extract_links(
                        scrape_result["data"]["html"],
                        url
                    )
                    
                    async with self._lock:
                        for link in new_links:
                            await queue_manager.add_url(link, depth + 1, url)
                
                # Store the page
                async with self._lock:
                    response.pages.append(page)
                    response.stats.success_count += 1
                    logger.info(f"Successfully processed {url}")
            
            else:
                async with self._lock:
                    response.stats.failed_count += 1
                logger.error(f"Failed to scrape {url}")
                
        except Exception as e:
            async with self._lock:
                response.stats.failed_count += 1
            logger.error(f"Error processing {url}: {str(e)}")
            
        finally:
            await queue_manager.mark_complete(url)

    
    async def crawl_sync(self, request: CrawlerRequest) -> CrawlerResponse:
        """
        Perform synchronous crawl and wait for completion.
        """
        logger.info(f"Starting synchronous crawl for {request.url}")
        
        # Initialize components
        queue_manager = QueueManager(request)
        link_extractor = LinkExtractor(request)
        
        # Create response object
        response = CrawlerResponse(
            crawl_id=request.crawl_id,
            status=CrawlStatus.IN_PROGRESS,
            stats=CrawlStats(
                total_pages=0,
                success_count=0,
                failed_count=0,
                skipped_count=0,
                start_time=datetime.utcnow()
            )
        )
        
        try:
            # Add initial URL
            logger.debug("Adding initial URL to queue")
            await queue_manager.add_url(str(request.url))
            
            while True:
                # Check completion conditions first
                if queue_manager.is_complete:
                    logger.debug("Queue is complete, breaking")
                    break

                if len(response.pages) >= request.max_pages:
                    logger.info(f"Reached max pages limit: {request.max_pages}")
                    break

                # Get URLs to process
                processing_urls = []
                async with self._lock:
                    # Get batch of URLs to process
                    remaining_slots = request.max_pages - len(response.pages)
                    batch_size = min(self.worker_threads, remaining_slots)
                    
                    for _ in range(batch_size):
                        url = await queue_manager.get_next_url()
                        if url:
                            processing_urls.append(url)
                
                if not processing_urls:
                    # No URLs available, check if we're really done
                    if not queue_manager.in_progress and queue_manager.queue.empty():
                        logger.debug("No URLs in queue and none in progress, breaking")
                        break
                    await asyncio.sleep(0.1)
                    continue
                
                # Process URLs in parallel
                tasks = []
                for url in processing_urls:
                    depth = queue_manager.get_depth(url)
                    task = asyncio.create_task(
                        self._process_page(
                            url=url,
                            depth=depth,
                            queue_manager=queue_manager,
                            link_extractor=link_extractor,
                            response=response,
                            request=request
                        )
                    )
                    tasks.append(task)
                
                if tasks:
                    await asyncio.gather(*tasks)
                    logger.debug(f"Processed batch of {len(tasks)} URLs")
            
            # Update final statistics
            response.status = CrawlStatus.COMPLETED
            response.stats.end_time = datetime.utcnow()
            response.stats.duration_seconds = (
                response.stats.end_time - response.stats.start_time
            ).total_seconds()
            response.stats.total_pages = len(response.pages)
            
            logger.info(f"Crawl completed. Processed {len(response.pages)} pages in {response.stats.duration_seconds:.2f} seconds")
            return response
            
        except Exception as e:
            logger.exception(f"Crawl failed: {str(e)}")
            response.status = CrawlStatus.FAILED
            response.error = str(e)
            return response

    async def start_crawl(self, request: CrawlerRequest) -> CrawlerResponse:
        """Start an asynchronous crawl (for background processing)"""
        logger.info(f"Starting asynchronous crawl for {request.url}")
        
        response = CrawlerResponse(
            crawl_id=request.crawl_id,
            status=CrawlStatus.IN_PROGRESS,
            stats=CrawlStats(
                total_pages=0,
                success_count=0,
                failed_count=0,
                skipped_count=0,
                start_time=datetime.utcnow()
            )
        )
        
        self.active_crawls[request.crawl_id] = response
        asyncio.create_task(self.crawl_sync(request))
        return response

    async def cleanup(self):
        """Cleanup resources"""
        try:
            self._executor.shutdown(wait=False)
            await self.scraper.cleanup()
            self.active_crawls.clear()
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
