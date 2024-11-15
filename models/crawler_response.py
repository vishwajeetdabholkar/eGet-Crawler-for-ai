from pydantic import BaseModel, HttpUrl, Field
from typing import List, Dict, Optional, Any
from uuid import UUID
from enum import Enum
from datetime import datetime

class CrawlStatus(str, Enum):
    """Enum for crawl status"""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class CrawledPage(BaseModel):
    """Model for individual crawled page data"""
    url: HttpUrl
    markdown: str
    structured_data: Dict[str, Any]
    scrape_id: UUID
    crawled_at: datetime = Field(default_factory=datetime.utcnow)
    depth: int = Field(ge=0)
    parent_url: Optional[HttpUrl] = None
    class Config:
        arbitrary_types_allowed = True

class CrawlStats(BaseModel):
    """Model for crawl statistics"""
    total_pages: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None

class CrawlerResponse(BaseModel):
    """
    Response model for the crawler endpoint.
    
    Attributes:
        crawl_id (UUID): Unique identifier for the crawl
        status (CrawlStatus): Current status of the crawl
        pages (List[CrawledPage]): List of crawled pages and their data
        stats (CrawlStats): Statistics about the crawl
        error (Optional[str]): Error message if crawl failed
    """
    crawl_id: UUID
    status: CrawlStatus
    pages: List[CrawledPage] = Field(default_factory=list)
    stats: CrawlStats
    error: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "crawl_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "completed",
                "pages": [
                    {
                        "url": "https://example.com",
                        "markdown": "# Example Page\nContent here...",
                        "metadata": {
                            "title": "Example Page",
                            "description": "An example page",
                            "language": "en",
                            "sourceURL": "https://example.com",
                            "url": "https://example.com",
                            "statusCode": 200
                        },
                        "scrape_id": "123e4567-e89b-12d3-a456-426614174001",
                        "depth": 0
                    }
                ],
                "stats": {
                    "total_pages": 1,
                    "success_count": 1,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "start_time": "2024-03-20T12:00:00Z",
                    "end_time": "2024-03-20T12:00:10Z",
                    "duration_seconds": 10.0
                }
            }
        }