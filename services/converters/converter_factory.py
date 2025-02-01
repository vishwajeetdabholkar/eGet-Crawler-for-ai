from typing import Type, Dict
from loguru import logger
from models.file_conversion_models import FileType
from .base_converter import BaseDocumentConverter

class ConverterFactory:
    """Factory class for creating document converters"""
    
    _converters: Dict[FileType, Type[BaseDocumentConverter]] = {}
    
    @classmethod
    def register_converter(cls, file_type: FileType, 
                         converter_class: Type[BaseDocumentConverter]) -> None:
        """Register a converter class for a file type"""
        cls._converters[file_type] = converter_class
        logger.info(f"Registered converter {converter_class.__name__} for {file_type.value}")
    
    @classmethod
    def get_converter(cls, file_type: FileType) -> BaseDocumentConverter:
        """Get converter instance for file type"""
        converter_class = cls._converters.get(file_type)
        if not converter_class:
            raise ValueError(f"No converter registered for file type: {file_type.value}")
        return converter_class()
    
    @classmethod
    def supported_types(cls) -> list[str]:
        """Get list of supported file types"""
        return [ft.value for ft in cls._converters.keys()]

# Import and register converters
def register_converters():
    """Register all available converters"""
    from .converters.pdf_converter import PDFConverter
    from .converters.docx_converter import DocxConverter
    from .converters.xlsx_converter import XlsxConverter
    # from pptx_converter import PptxConverter
    
    ConverterFactory.register_converter(FileType.PDF, PDFConverter)
    ConverterFactory.register_converter(FileType.DOCX, DocxConverter)
    ConverterFactory.register_converter(FileType.XLSX, XlsxConverter)
    # ConverterFactory.register_converter(FileType.PPTX, PptxConverter)