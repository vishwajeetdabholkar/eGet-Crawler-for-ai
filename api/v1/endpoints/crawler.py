from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from models.crawler_request import CrawlerRequest
from models.crawler_response import CrawlerResponse, CrawlStatus  
from services.crawler.crawler_service import CrawlerService
from loguru import logger

router = APIRouter()
crawler_service = CrawlerService(max_concurrent=3, worker_threads=2)

@router.post("/crawl", response_model=List[Dict[str, Any]])  # Changed this line
async def start_crawl(request: CrawlerRequest):
    """
    Start a new crawl operation.
    
    Args:
        request (CrawlerRequest): Crawl request parameters
        
    Returns:
        List[Dict[str, str]]: List of crawled pages with URLs and markdown content
    """
    try:
        logger.info(f"Starting new crawl for URL: {request.url}")
        results = await crawler_service.crawl_sync(request)
        logger.info(f"Crawl completed. Status: {results.status}, Pages: {len(results.pages)}")

        if results.status != CrawlStatus.COMPLETED:
            raise HTTPException(
                status_code=500, 
                detail=f"Crawl failed with status: {results.status}. Error: {results.error}"
            )
        
        # Transform to simplified format
        full_results = [
            {
                "url": str(page.url),
                "markdown": page.markdown,
                "structured_data": page.structured_data  # Only include structured_data
            }
            for page in results.pages
        ]
        
        logger.info(f"Transformed {len(full_results)} pages for response")
        return full_results
        
    except Exception as e:
        logger.error(f"Failed to crawl: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))