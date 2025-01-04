from typing import Dict, Type
from fastapi import UploadFile
import asyncio
from loguru import logger
from services.cache.cache_service import CacheService
from models.file_conversion_models import (
    FileType, FileMetadata, FileConversionResponse,
    ConversionWarning
)
from core.exceptions import FileConversionException
import hashlib

# Direct imports since all files are in the same directory
from .base_converter import BaseDocumentConverter, ConversionContext
from .document_structure import DocumentStructure, DocumentElement, ElementType
from .file_utils import FileUtils
from .converter_factory import ConverterFactory
from .converters.pdf_converter import PDFConverter
from .converters.docx_converter import DocxConverter
from .converters.xlsx_converter import XlsxConverter

# Register converters
ConverterFactory.register_converter(FileType.PDF, PDFConverter)
ConverterFactory.register_converter(FileType.DOCX, DocxConverter)
ConverterFactory.register_converter(FileType.XLSX, XlsxConverter)

class EnhancedConversionService:
    """Enhanced service for handling file to markdown conversions"""
    
    def __init__(self, cache_service: CacheService = None):
        self.cache_service = cache_service
        self.converters: Dict[FileType, Type[BaseDocumentConverter]] = {
            FileType.PDF: PDFConverter,
            FileType.DOCX: DocxConverter,
            FileType.XLSX: XlsxConverter
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
                supported_types = [t.value for t in self.converters.keys()]
                return FileConversionResponse(
                    success=False,
                    error=f"Unsupported file type. Supported types: {', '.join(supported_types)}"
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
                cache_options = {
                    'filename': file.filename,
                    'file_type': file_type.value,
                    'max_size_mb': max_size_mb
                }
                cached_result = await self.cache_service.get_cached_result(cache_key, cache_options)
                
                if cached_result:
                    logger.info(f"Cache hit for {file.filename}")
                    return FileConversionResponse(**cached_result)
            
            # Create conversion context
            context = ConversionContext(
                filename=file.filename,
                size_bytes=len(content),
                source_format=file_type.value,
                conversion_options={
                    'max_size_mb': max_size_mb
                }
            )
            
            # Get converter instance from our dictionary
            converter_class = self.converters.get(file_type)
            if not converter_class:
                return FileConversionResponse(
                    success=False,
                    error=f"No converter available for {file_type.value}"
                )
                
            converter = converter_class()
            
            # Convert file
            try:
                markdown_content, metadata = await converter.convert(content, context)
            except Exception as e:
                logger.error(f"Conversion error for {file.filename}: {str(e)}")
                raise FileConversionException(f"Failed to convert {file_type.value}: {str(e)}")
            
            result = FileConversionResponse(
                success=True,
                markdown=markdown_content,
                metadata=metadata,
                warnings=[ConversionWarning(
                    code="WARNING",
                    message=warning
                ) for warning in context.warnings] if context.warnings else []
            )
            
            # Cache result if enabled
            if self.cache_service:
                from datetime import timedelta
                await self.cache_service.cache_result(
                    cache_key,
                    cache_options,
                    result.dict(),
                    ttl=timedelta(hours=1)
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


# For backward compatibility, create alias
ConversionService = EnhancedConversionService