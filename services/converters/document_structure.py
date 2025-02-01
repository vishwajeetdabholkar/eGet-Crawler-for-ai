from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

class ElementType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    IMAGE = "image"
    CODE = "code"
    MATH = "math"
    METADATA = "metadata"
    FOOTNOTE = "footnote"
    CITATION = "citation"
    SEPARATOR = "separator"

@dataclass
class DocumentElement:
    """Represents a semantic element in the document"""
    type: ElementType
    content: Union[str, List[str], Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    level: Optional[int] = None
    children: List['DocumentElement'] = field(default_factory=list)
    
    @property
    def is_container(self) -> bool:
        """Check if element can contain other elements"""
        return self.type in {ElementType.HEADING}

class DocumentStructure:
    """Manages document structure and hierarchy"""
    
    def __init__(self):
        self.elements: List[DocumentElement] = []
        self._current_section: Optional[DocumentElement] = None
        self._section_stack: List[DocumentElement] = []
    
    def add_element(self, element: DocumentElement) -> None:
        """Add element maintaining document hierarchy"""
        if element.type == ElementType.HEADING:
            self._handle_heading(element)
        elif self._current_section and self._current_section.is_container:
            self._current_section.children.append(element)
        else:
            self.elements.append(element)
    
    def _handle_heading(self, heading: DocumentElement) -> None:
        """Handle heading hierarchy"""
        # Pop sections of equal or higher level
        while (self._section_stack and 
               self._section_stack[-1].level is not None and 
               self._section_stack[-1].level >= heading.level):
            self._section_stack.pop()
        
        # Add to parent section or root
        if self._section_stack:
            self._section_stack[-1].children.append(heading)
        else:
            self.elements.append(heading)
        
        # Update current section
        self._section_stack.append(heading)
        self._current_section = heading
    
    def to_markdown(self) -> str:
        """Convert document structure to markdown"""
        return self._process_elements(self.elements)
    
    def _process_elements(self, elements: List[DocumentElement], level: int = 0) -> str:
        """Process list of elements into markdown"""
        md_parts = []
        
        for element in elements:
            # Process element content
            content = self._process_element(element, level)
            if content:
                md_parts.append(content)
            
            # Process children if any
            if element.children:
                child_content = self._process_elements(element.children, level + 1)
                if child_content:
                    md_parts.append(child_content)
        
        return '\n\n'.join(part.strip() for part in md_parts if part.strip())
    
    def _process_element(self, element: DocumentElement, level: int) -> str:
        """Convert single element to markdown"""
        if element.type == ElementType.HEADING:
            return f"{'#' * element.level} {element.content}"
            
        elif element.type == ElementType.PARAGRAPH:
            return str(element.content)
            
        elif element.type == ElementType.LIST:
            items = element.content if isinstance(element.content, list) else [element.content]
            ordered = element.metadata.get('ordered', False)
            indent = "    " * level
            
            if ordered:
                return '\n'.join(f"{indent}{i}. {item}" 
                               for i, item in enumerate(items, 1))
            else:
                return '\n'.join(f"{indent}- {item}" for item in items)
                
        elif element.type == ElementType.TABLE:
            if isinstance(element.content, list):
                headers = element.metadata.get('has_headers', True)
                align = element.metadata.get('align', ['left'] * len(element.content[0]))
                
                return self._format_table(element.content, headers, align)
                
        elif element.type == ElementType.IMAGE:
            alt = element.metadata.get('alt', 'Image')
            return f"![{alt}]({element.content})"
            
        elif element.type == ElementType.CODE:
            lang = element.metadata.get('language', '')
            return f"```{lang}\n{element.content}\n```"
            
        elif element.type == ElementType.MATH:
            inline = element.metadata.get('inline', False)
            if inline:
                return f"${element.content}$"
            return f"$$\n{element.content}\n$$"
            
        elif element.type == ElementType.SEPARATOR:
            return "---"
            
        return ""
    
    def _format_table(self, rows: List[List[str]], 
                     headers: bool = True,
                     align: List[str] = None) -> str:
        """Format table with alignment support"""
        if not rows or not rows[0]:
            return ""
            
        # Calculate column widths
        col_widths = [0] * len(rows[0])
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # Default left alignment
        if not align:
            align = ['left'] * len(col_widths)
        
        # Build table
        md_lines = []
        
        # Header/first row
        md_lines.append(self._format_row(rows[0], col_widths))
        
        # Separator with alignment
        separators = []
        for width, alignment in zip(col_widths, align):
            if alignment == 'center':
                sep = f":{'-' * (width)}:"
            elif alignment == 'right':
                sep = f"{'-' * (width)}:"
            else:  # left or default
                sep = f":{'-' * (width)}"
            separators.append(sep)
        md_lines.append(f"|{'|'.join(separators)}|")
        
        # Data rows
        if headers:
            start_idx = 1
        else:
            start_idx = 0
        
        for row in rows[start_idx:]:
            md_lines.append(self._format_row(row, col_widths))
        
        return '\n'.join(md_lines)
    
    def _format_row(self, row: List[str], widths: List[int]) -> str:
        """Format table row with proper cell padding"""
        cells = []
        for cell, width in zip(row, widths):
            cell_str = str(cell).replace('|', '\\|')
            cells.append(f" {cell_str:<{width}} ")
        return f"|{'|'.join(cells)}|"