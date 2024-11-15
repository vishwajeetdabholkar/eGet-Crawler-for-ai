from pydantic import BaseModel, HttpUrl, validator, Field
from typing import Optional, List, Pattern
import re
from uuid import UUID, uuid4

class CrawlerRequest(BaseModel):
    """
    Request model for the crawler endpoint.
    
    Attributes:
        url (HttpUrl): The root URL to start crawling from
        max_depth (int): Maximum depth of pages to crawl from root URL
        max_pages (int): Maximum number of pages to crawl
        exclude_patterns (List[str]): URL patterns to exclude from crawling
        include_patterns (List[str]): URL patterns to specifically include
        respect_robots_txt (bool): Whether to respect robots.txt rules
        crawl_id (UUID): Unique identifier for the crawl request
    """
    url: HttpUrl
    max_depth: Optional[int] = Field(default=3, ge=1, le=10, description="Maximum depth to crawl")
    max_pages: Optional[int] = Field(default=100, ge=1, le=1000, description="Maximum pages to crawl")
    exclude_patterns: Optional[List[str]] = Field(default=[], description="URL patterns to exclude")
    include_patterns: Optional[List[str]] = Field(default=[], description="URL patterns to specifically include")
    respect_robots_txt: Optional[bool] = Field(default=True, description="Whether to respect robots.txt")
    crawl_id: UUID = Field(default_factory=uuid4, description="Unique identifier for the crawl")

    @validator('exclude_patterns', 'include_patterns')
    def validate_patterns(cls, v):
        """Validate that patterns are valid regex expressions"""
        if v:
            for pattern in v:
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise ValueError(f"Invalid regex pattern: {pattern}, error: {str(e)}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com",
                "max_depth": 3,
                "max_pages": 100,
                "exclude_patterns": [r"\/api\/.*", r".*\.(jpg|jpeg|png|gif)$"],
                "include_patterns": [r"\/blog\/.*", r"\/docs\/.*"],
                "respect_robots_txt": True
            }
        }