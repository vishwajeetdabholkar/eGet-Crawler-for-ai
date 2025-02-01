from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

class ChunkRequest(BaseModel):
    """Request model for the chunking endpoint"""
    url: HttpUrl
    max_chunk_size: Optional[int] = Field(default=512, ge=128, le=2048)
    min_chunk_size: Optional[int] = Field(default=128, ge=64, le=512)
    preserve_code_blocks: Optional[bool] = Field(default=True)
    include_metadata: Optional[bool] = Field(default=True)
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com/docs",
                "max_chunk_size": 512,
                "min_chunk_size": 128,
                "preserve_code_blocks": True,
                "include_metadata": True
            }
        }