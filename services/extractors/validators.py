from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, HttpUrl, validator

class JsonLdData(BaseModel):
    """Validates JSON-LD data"""
    @validator('*')
    def check_required_fields(cls, v):
        if isinstance(v, dict):
            if not v.get('@context') or not v.get('@type'):
                raise ValueError("JSON-LD must contain @context and @type")
        return v

class OpenGraphData(BaseModel):
    """Validates OpenGraph data"""
    title: Optional[str]
    description: Optional[str]
    url: Optional[HttpUrl]
    type: Optional[str]
    image: Optional[str]
    
    class Config:
        extra = 'allow'

class TwitterCardData(BaseModel):
    """Validates Twitter Card data"""
    card: Optional[str]
    title: Optional[str]
    description: Optional[str]
    
    class Config:
        extra = 'allow'

class MetaData(BaseModel):
    """Validates Meta data"""
    description: Optional[str]
    keywords: Optional[str]
    language: Optional[str] = None
    
    class Config:
        extra = 'allow'
        
        @classmethod
        def get_properties(cls):
            return {
                'description': None,
                'keywords': None,
                'language': None
            }

class StructuredDataValidator(BaseModel):
    """Main validator for all structured data"""
    jsonLd: Optional[List[Dict[str, Any]]] = []
    openGraph: Optional[Dict[str, str]] = {}
    twitterCard: Optional[Dict[str, str]] = {}
    metaData: Optional[Dict[str, str]] = {
        'language': None  # Explicitly set default None
    }

    class Config:
        extra = 'allow'
        validate_assignment = True
        
        @classmethod
        def get_default_metadata(cls):
            return {
                'language': None,
            }
            
    @validator('metaData')
    def ensure_metadata_fields(cls, v):
        """Ensure required metadata fields exist"""
        if v is None:
            v = {}
        # Ensure language field exists, even if None
        if 'language' not in v:
            v['language'] = None
        return v