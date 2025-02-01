from fastapi import APIRouter, Depends, Request
from models.chunk_request import ChunkRequest
from models.chunk_response import ChunkResponse
from services.chunker.chunk_service import ChunkService
from loguru import logger

router = APIRouter(tags=["chunker"])

@router.post("/chunk", response_model=ChunkResponse)
async def chunk_url(request: ChunkRequest, req: Request):
    """
    Process URL and return semantic chunks
    """
    try:
        # Get scraper from app state
        if not hasattr(req.app.state, "scraper"):
            raise Exception("Scraper service not initialized")
            
        # Initialize chunk service
        chunk_service = ChunkService(req.app.state.scraper)
        
        # Process the URL
        result = await chunk_service.process_url(request)
        return result
        
    except Exception as e:
        logger.exception(f"Chunking error: {str(e)}")
        return ChunkResponse(
            success=False,
            markdown="",
            chunks=[],
            error=str(e)
        )