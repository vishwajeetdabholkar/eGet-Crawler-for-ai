from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any

class Action(BaseModel):
    type: str
    milliseconds: Optional[int]
    selector: Optional[str]

class Location(BaseModel):
    country: Optional[str]
    languages: Optional[List[str]]

class ExtractConfig(BaseModel):
    custom_config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    prompt: Optional[str] = None

class ScrapeRequest(BaseModel):
    url: HttpUrl
    formats: List[str]
    onlyMainContent: Optional[bool] = True
    includeTags: Optional[List[str]] = None
    excludeTags: Optional[List[str]] = None
    headers: Optional[Dict[str, str]] = None
    waitFor: Optional[int] = None
    mobile: Optional[bool] = False
    skipTlsVerification: Optional[bool] = False
    timeout: Optional[int] = None
    extract: Optional[ExtractConfig] = None
    actions: Optional[List[Action]] = None
    location: Optional[Location] = None
    
    includeRawHtml: Optional[bool] = False
    includeScreenshot: Optional[bool] = False