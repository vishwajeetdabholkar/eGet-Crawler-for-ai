from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Response
from typing import Optional
from models.file_conversion_models import FileConversionResponse, FileType
from services.converters.conversion_service import ConversionService
from core.config import settings
from services.cache.cache_service import CacheService
from prometheus_client import Counter, Histogram
from loguru import logger

# Metrics
CONVERSION_REQUESTS = Counter('file_conversion_requests_total', 'Total file conversion requests')
CONVERSION_ERRORS = Counter('file_conversion_errors_total', 'Total file conversion errors')
CONVERSION_DURATION = Histogram('file_conversion_duration_seconds', 'Time spent converting files')

router = APIRouter(tags=["converter"])

async def get_conversion_service() -> ConversionService:
    """Dependency to get conversion service instance"""
    # Initialize cache service if enabled
    cache_service = None
    if settings.CACHE_ENABLED:
        cache_service = CacheService(settings.REDIS_URL)
        await cache_service.connect()
    return ConversionService(cache_service=cache_service)

@router.post(
    "/convert/file",
    response_model=FileConversionResponse,
    responses={
        413: {"description": "File too large"},
        415: {"description": "Unsupported file type"},
        422: {"description": "Validation error"},
        500: {"description": "Server error"}
    }
)
async def convert_file(
    file: UploadFile = File(...),
    service: ConversionService = Depends(get_conversion_service),
    response: Response = None,
) -> FileConversionResponse:
    """
    Convert supported document types to markdown.
    
    Supported file types:
    - PDF (.pdf)
    - Word (.docx)
    - Excel (.xlsx)
    - PowerPoint (.pptx)
    
    Maximum file size: 5MB
    """
    CONVERSION_REQUESTS.inc()
    
    try:
        # Validate file type
        file_type = FileType.from_extension(file.filename)
        if not file_type:
            CONVERSION_ERRORS.inc()
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type. Supported types: {', '.join(t.value for t in FileType)}"
            )
        
        # Convert file with metrics
        with CONVERSION_DURATION.time():
            result = await service.convert_file(file)
            
        if not result.success:
            CONVERSION_ERRORS.inc()
            raise HTTPException(
                status_code=500,
                detail=result.error or "Conversion failed"
            )
        
        # Set cache headers if result was cached
        if hasattr(result, 'cached') and result.cached:
            response.headers['X-Cache'] = 'HIT'
        else:
            response.headers['X-Cache'] = 'MISS'
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        CONVERSION_ERRORS.inc()
        logger.exception("Unexpected error during file conversion")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )