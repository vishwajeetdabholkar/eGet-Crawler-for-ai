from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, List, Optional
from dataclasses import dataclass
import unicodedata
import re
from loguru import logger
from models.file_conversion_models import FileMetadata

@dataclass
class ConversionContext:
    """Holds context information during conversion process"""
    filename: str
    size_bytes: int
    source_format: str
    conversion_options: Dict[str, Any] = None
    temp_files: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        self.temp_files = self.temp_files or []
        self.warnings = self.warnings or []
        self.conversion_options = self.conversion_options or {}

class BaseDocumentConverter(ABC):
    """Abstract base class for document converters"""
    
    def __init__(self):
        self.context: Optional[ConversionContext] = None
    
    @abstractmethod
    async def convert(self, content: bytes, context: ConversionContext) -> Tuple[str, FileMetadata]:
        """Convert document content to markdown"""
        pass
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        if not text:
            return ""
            
        # Remove control characters except newlines and tabs
        text = ''.join(char if char in '\n\t' or not unicodedata.category(char).startswith('C') 
                      else ' ' for char in text)
        
        # Normalize whitespace
        text = re.sub(r'[^\S\n]+', ' ', text)
        
        # Normalize newlines (max 2 consecutive)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove whitespace at start/end of lines
        text = '\n'.join(line.strip() for line in text.split('\n'))
        
        return text.strip()
    
    def _format_table(self, rows: List[List[str]], headers: bool = True) -> str:
        """Convert table data to markdown format"""
        if not rows or not rows[0]:
            return ""
            
        # Clean cell data and calculate column widths
        cleaned_rows = []
        col_widths = [0] * len(rows[0])
        
        for row in rows:
            cleaned_row = []
            for i, cell in enumerate(row):
                cell_str = str(cell).replace('|', '\\|').strip()
                cleaned_row.append(cell_str)
                col_widths[i] = max(col_widths[i], len(cell_str))
            cleaned_rows.append(cleaned_row)
        
        # Build markdown table
        md_lines = []
        
        # Header row
        md_lines.append('| ' + ' | '.join(f'{cell:{width}}' 
                       for cell, width in zip(cleaned_rows[0], col_widths)) + ' |')
        
        # Separator
        md_lines.append('|' + '|'.join(f':{"-"*(width)}:' 
                       for width in col_widths) + '|')
        
        # Data rows
        if headers:
            start_idx = 1
        else:
            start_idx = 0
            
        for row in cleaned_rows[start_idx:]:
            md_lines.append('| ' + ' | '.join(f'{cell:{width}}' 
                          for cell, width in zip(row, col_widths)) + ' |')
        
        return '\n'.join(md_lines)
    
    def _format_list(self, items: List[str], ordered: bool = False, 
                    level: int = 0) -> str:
        """Convert list items to markdown format"""
        if not items:
            return ""
            
        indent = "    " * level
        md_lines = []
        
        for i, item in enumerate(items, 1):
            prefix = f"{i}." if ordered else "-"
            md_lines.append(f"{indent}{prefix} {item.strip()}")
        
        return '\n'.join(md_lines)
    
    def log_warning(self, message: str):
        """Log a warning and add to context if available"""
        logger.warning(message)
        if self.context:
            self.context.warnings.append(message)