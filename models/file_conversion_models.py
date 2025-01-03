from pydantic import BaseModel, conint, validator
from typing import Optional, Dict, List
from enum import Enum
import os

class FileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    
    @classmethod
    def from_extension(cls, filename: str) -> Optional['FileType']:
        ext = os.path.splitext(filename)[1].lower().lstrip('.')
        try:
            return cls(ext)
        except ValueError:
            return None

class FileMetadata(BaseModel):
    filename: str
    size_bytes: int
    file_type: FileType
    pages: Optional[int] = None
    tables_count: Optional[int] = None
    images_count: Optional[int] = None
    equations_count: Optional[int] = None
    
class ConversionWarning(BaseModel):
    code: str
    message: str
    details: Optional[Dict] = None

class FileConversionResponse(BaseModel):
    success: bool
    markdown: Optional[str] = None  # Make it optional with default None
    metadata: Optional[FileMetadata] = None  # Make it optional with default None
    warnings: List[ConversionWarning] = []
    error: Optional[str] = None
    
    @validator('markdown')
    def validate_markdown_content(cls, v, values):
        if values.get('success') and not v:
            raise ValueError("Markdown content must be present when success is True")
        return v