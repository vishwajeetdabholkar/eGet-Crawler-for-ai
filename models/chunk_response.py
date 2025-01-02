from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

class ChunkMetadata(BaseModel):
    """Metadata for each chunk"""
    # Modified fields to match what our semantic chunker produces
    heading: Optional[str] = None
    code_language: Optional[str] = None  # Made optional with default None
    word_count: int
    position: int
    type: str = Field(..., description="section|paragraph|code|list|table")
    # New optional fields for better semantic understanding
    start_idx: Optional[int] = None
    end_idx: Optional[int] = None
    sentence_count: Optional[int] = None

class ChunkHierarchy(BaseModel):
    """Hierarchy information for chunks"""
    parent_id: Optional[UUID] = None
    level: int
    path: List[str]

class Chunk(BaseModel):
    """Individual chunk model"""
    id: UUID
    content: str
    type: str
    hierarchy: ChunkHierarchy
    metadata: ChunkMetadata
    model_config = ConfigDict(from_attributes=True)

class ChunkResponse(BaseModel):
    """Response model for the chunking endpoint"""
    success: bool
    markdown: str
    chunks: List[Chunk]
    stats: Dict[str, Any] = Field(
        default_factory=lambda: {
            "total_chunks": 0,
            "avg_chunk_size": 0,
            "processing_time": 0
        }
    )
    error: Optional[str] = None
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    model_config = ConfigDict(from_attributes=True)