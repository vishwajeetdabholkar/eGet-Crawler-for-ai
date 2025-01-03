from typing import Dict, Type
from fastapi import UploadFile
import asyncio
from loguru import logger
from services.cache.cache_service import CacheService
from services.converters.markdown_converter import (
    BaseConverter, PDFConverter, DocxConverter, 
    XlsxConverter, PptxConverter
)
from models.file_conversion_models import (
    FileType, FileMetadata, FileConversionResponse,
    ConversionWarning
)
from core.exceptions import FileConversionException
import hashlib

class ConversionService:
    """Service for handling file to markdown conversions"""
    
    def __init__(self, cache_service: CacheService = None):
        self.cache_service = cache_service
        self.converters: Dict[FileType, Type[BaseConverter]] = {
            FileType.PDF: PDFConverter,
            FileType.DOCX: DocxConverter,
            FileType.XLSX: XlsxConverter,
            FileType.PPTX: PptxConverter
        }
    
    def _get_cache_key(self, file_content: bytes, file_type: str) -> str:
        """Generate cache key based on file content hash"""
        content_hash = hashlib.sha256(file_content).hexdigest()
        return f"file_conversion:{file_type}:{content_hash}"
    
    async def convert_file(self, file: UploadFile, 
                          max_size_mb: int = 5) -> FileConversionResponse:
        """Convert uploaded file to markdown"""
        try:
            # Validate file type
            file_type = FileType.from_extension(file.filename)
            if not file_type:
                return FileConversionResponse(
                    success=False,
                    error=f"Unsupported file type. Supported types: {', '.join(t.value for t in FileType)}"
                )
            
            # Read file content
            content = await file.read()
            file_size_mb = len(content) / (1024 * 1024)
            
            # Check file size
            if file_size_mb > max_size_mb:
                return FileConversionResponse(
                    success=False,
                    error=f"File size exceeds {max_size_mb}MB limit"
                )
            
            # Check cache if enabled
            if self.cache_service:
                cache_key = self._get_cache_key(content, file_type.value)
                cached_result = await self.cache_service.get_cached_result(cache_key, {})
                
                if cached_result:
                    return FileConversionResponse(**cached_result)
            
            # Get appropriate converter
            converter = self.converters[file_type]()
            
            # Convert file
            markdown_content, metadata = await converter.convert(content)
            
            result = FileConversionResponse(
                success=True,
                markdown=markdown_content,
                metadata=metadata
            )
            
            # Cache result if enabled
            from datetime import timedelta
            await self.cache_service.cache_result(
                cache_key, 
                {}, 
                result.dict(),
                ttl=timedelta(seconds=3600)  # Pass timedelta object instead of int
            )
            
            return result
            
        except FileConversionException as e:
            logger.error(f"Conversion error: {str(e)}")
            return FileConversionResponse(
                success=False,
                error=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error during conversion: {str(e)}")
            return FileConversionResponse(
                success=False,
                error="An unexpected error occurred during conversion"
            )
        finally:
            await file.seek(0)  # Reset file pointer