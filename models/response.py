from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Metadata(BaseModel):
    title: Optional[str]
    description: Optional[str]
    language: Optional[str]
    sourceURL: str
    statusCode: int
    error: Optional[str]

class Actions(BaseModel):
    screenshots: Optional[List[str]]

class StructuredData(BaseModel):
    jsonLd: Optional[List[Dict[str, Any]]] = None
    openGraph: Optional[Dict[str, str]] = None
    twitterCard: Optional[Dict[str, str]] = None
    metaData: Optional[Dict[str, str]] = None
    
class ScrapeData(BaseModel):
    markdown: Optional[str]
    html: Optional[str]
    rawHtml: Optional[str]
    screenshot: Optional[str]
    links: Optional[List[str]]
    actions: Optional[Actions]
    metadata: Metadata
    llm_extraction: Optional[Dict[str, Any]]
    warning: Optional[str]
    structured_data: Optional[StructuredData] = None

class ScrapeResponse(BaseModel):
    success: bool
    data: Optional[ScrapeData]

