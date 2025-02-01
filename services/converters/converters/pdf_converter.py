import PyPDF2
from typing import Dict, Any, List, Tuple, Optional, Set
import re
from io import BytesIO
from datetime import datetime
from loguru import logger
from ..base_converter import BaseDocumentConverter, ConversionContext
from ..document_structure import DocumentStructure, DocumentElement, ElementType
from ..file_utils import FileUtils
from models.file_conversion_models import FileMetadata, FileType

class PDFConverter(BaseDocumentConverter):
    """Enhanced PDF to Markdown converter with semantic structure preservation"""
    
    def __init__(self):
        super().__init__()
        self.structure = DocumentStructure()
        self.file_utils = FileUtils()
        self._temp_files = []
        self._image_counter = 0
        self._current_page = 0
        
    async def convert(self, content: bytes, context: ConversionContext) -> Tuple[str, FileMetadata]:
        """Convert PDF file to markdown"""
        self.context = context
        temp_path = None
        images_found = []
        tables_found = []
        
        try:
            # Create temporary file
            temp_path = self.file_utils.create_temp_file(content, '.pdf')
            self._temp_files.append(temp_path)
            
            # Open PDF file
            with open(temp_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                
                # Add document metadata
                self._add_document_metadata(reader)
                
                # Process each page
                for page_num, page in enumerate(reader.pages, 1):
                    self._current_page = page_num
                    
                    # Add page marker
                    self._add_page_marker(page_num)
                    
                    # Extract and process content
                    extracted_images = self._extract_images(page)
                    images_found.extend(extracted_images)
                    
                    extracted_tables = self._extract_tables(page)
                    tables_found.extend(extracted_tables)
                    
                    # Extract and process text content
                    text_content = self._extract_text_with_formatting(page)
                    self._process_text_content(text_content)
            
            # Convert to markdown
            markdown_content = self.structure.to_markdown()
            
            # Create metadata
            metadata = FileMetadata(
                filename=context.filename,
                size_bytes=context.size_bytes,
                file_type=FileType.PDF,
                pages=len(reader.pages),
                images_count=len(images_found),
                tables_count=len(tables_found),
                equations_count=None  # PDF doesn't reliably expose equation data
            )
            
            return markdown_content, metadata
            
        except Exception as e:
            logger.error(f"PDF conversion error: {str(e)}")
            raise
        finally:
            # Cleanup temporary files
            self.file_utils.cleanup_temp_files(self._temp_files)
    
    def _add_document_metadata(self, reader: PyPDF2.PdfReader) -> None:
        """Add PDF document metadata to structure"""
        try:
            if reader.metadata:
                # Clean and format metadata
                metadata = {
                    key.strip('/'): value 
                    for key, value in reader.metadata.items()
                    if value and isinstance(value, (str, int, float, bool))
                }
                
                # Convert dates if present
                for key in ['CreationDate', 'ModDate']:
                    if key in metadata:
                        try:
                            # Handle PDF date format like "D:20220101120000+00'00'"
                            date_str = metadata[key].strip('D:').split('+')[0]
                            date = datetime.strptime(date_str, '%Y%m%d%H%M%S')
                            metadata[key] = date.isoformat()
                        except (ValueError, AttributeError):
                            pass
                
                self.structure.add_element(DocumentElement(
                    type=ElementType.METADATA,
                    content=metadata,
                    metadata={'source': 'pdf_metadata'}
                ))
                
        except Exception as e:
            self.log_warning(f"Error extracting PDF metadata: {str(e)}")
    
    def _add_page_marker(self, page_num: int) -> None:
        """Add page marker to document structure"""
        self.structure.add_element(DocumentElement(
            type=ElementType.HEADING,
            content=f"Page {page_num}",
            metadata={'type': 'page_marker', 'page_number': page_num},
            level=2
        ))
    
    def _extract_images(self, page: Any) -> List[Dict[str, Any]]:
        """Extract images from PDF page"""
        images = []
        try:
            if '/XObject' in page:
                xObject = page['/XObject'].get_object()
                
                for obj in xObject:
                    if xObject[obj]['/Subtype'] == '/Image':
                        image = xObject[obj]
                        try:
                            image_data = self._extract_image_data(image)
                            if image_data:
                                self._image_counter += 1
                                
                                # Get image format
                                format = self._determine_image_format(image)
                                
                                # Encode image
                                encoded_image = self.file_utils.encode_image(
                                    image_data, 
                                    format=format
                                )
                                
                                if encoded_image:
                                    # Add image to structure
                                    self.structure.add_element(DocumentElement(
                                        type=ElementType.IMAGE,
                                        content=encoded_image,
                                        metadata={
                                            'page': self._current_page,
                                            'image_number': self._image_counter,
                                            'width': image.get('/Width'),
                                            'height': image.get('/Height'),
                                            'bits': image.get('/BitsPerComponent'),
                                            'color_space': str(image.get('/ColorSpace')),
                                            'format': format
                                        }
                                    ))
                                    
                                    images.append({
                                        'format': format,
                                        'width': image.get('/Width'),
                                        'height': image.get('/Height')
                                    })
                                    
                        except Exception as e:
                            self.log_warning(f"Error extracting image: {str(e)}")
                            
        except Exception as e:
            self.log_warning(f"Error processing page images: {str(e)}")
            
        return images
    
    def _extract_image_data(self, image: Any) -> Optional[bytes]:
        """Extract raw image data based on filter type"""
        try:
            filter_type = image['/Filter']
            
            if isinstance(filter_type, list):
                filter_type = filter_type[0]
            
            if filter_type == '/FlateDecode':
                return image.get_data()
            elif filter_type in ['/DCTDecode', '/JPXDecode']:
                return image.get_data()
            elif filter_type == '/CCITTFaxDecode':
                return image.get_data()
                
        except Exception as e:
            self.log_warning(f"Error extracting image data: {str(e)}")
        return None
    
    def _determine_image_format(self, image: Any) -> str:
        """Determine image format from PDF image object"""
        filter_type = image['/Filter']
        if isinstance(filter_type, list):
            filter_type = filter_type[0]
            
        format_map = {
            '/DCTDecode': 'JPEG',
            '/JPXDecode': 'JP2',
            '/CCITTFaxDecode': 'PNG',
            '/FlateDecode': 'PNG'
        }
        
        return format_map.get(filter_type, 'PNG')
    
    def _extract_tables(self, page: Any) -> List[Dict[str, Any]]:
        """Extract tables from PDF page using positioning analysis"""
        tables = []
        try:
            text = page.extract_text()
            
            # Use regex patterns to identify potential tables
            table_patterns = [
                # Pattern for tables with grid lines (assuming consistent spacing)
                r'[\|\+][-\+]+[\|\+][\s\S]+?[\|\+][-\+]+[\|\+]',
                # Pattern for tables with consistent spacing
                r'(\s{2,}\S+){3,}[\s\S]+?(\s{2,}\S+){3,}'
            ]
            
            table_data = []
            for pattern in table_patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    table_text = match.group()
                    rows = self._parse_table_text(table_text)
                    if rows and len(rows) > 1:  # At least header and one data row
                        table_data.append(rows)
            
            # Add found tables to structure
            for table_rows in table_data:
                self.structure.add_element(DocumentElement(
                    type=ElementType.TABLE,
                    content=table_rows,
                    metadata={
                        'page': self._current_page,
                        'has_header': True
                    }
                ))
                
                tables.append({
                    'rows': len(table_rows),
                    'columns': len(table_rows[0]) if table_rows else 0
                })
                
        except Exception as e:
            self.log_warning(f"Error extracting tables: {str(e)}")
            
        return tables
    
    def _parse_table_text(self, table_text: str) -> List[List[str]]:
        """Parse table text into rows and columns"""
        rows = []
        lines = table_text.split('\n')
        
        for line in lines:
            # Skip separator lines
            if re.match(r'^[\|\+][-\+]+[\|\+]$', line):
                continue
                
            # Split by vertical bars or multiple spaces
            if '|' in line:
                cells = [cell.strip() for cell in line.split('|')]
                # Remove empty cells at start/end from vertical bars
                if not cells[0]:
                    cells = cells[1:]
                if not cells[-1]:
                    cells = cells[:-1]
            else:
                cells = [cell.strip() for cell in re.split(r'\s{2,}', line.strip())]
            
            if cells:
                rows.append(cells)
        
        return rows
    
    def _extract_text_with_formatting(self, page: Any) -> List[Dict[str, Any]]:
        """Extract text while preserving formatting"""
        elements = []
        try:
            text = page.extract_text()
            if not text.strip():
                return elements
                
            # Split into paragraphs
            paragraphs = text.split('\n\n')
            
            for para in paragraphs:
                if not para.strip():
                    continue
                    
                # Detect headers
                if self._is_heading(para):
                    level = self._determine_heading_level(para)
                    elements.append({
                        'type': 'heading',
                        'content': para.strip(),
                        'level': level
                    })
                    continue
                
                # Detect lists
                if self._is_list_item(para):
                    elements.append({
                        'type': 'list_item',
                        'content': para.strip()
                    })
                    continue
                
                # Regular paragraph
                elements.append({
                    'type': 'paragraph',
                    'content': para.strip()
                })
                
        except Exception as e:
            self.log_warning(f"Error extracting text: {str(e)}")
            
        return elements
    
    def _process_text_content(self, elements: List[Dict[str, Any]]) -> None:
        """Process extracted text elements"""
        current_list_items = []
        
        for element in elements:
            if element['type'] == 'heading':
                # If there's an ongoing list, flush it
                if current_list_items:
                    self._add_list_element(current_list_items)
                    current_list_items = []
                
                self.structure.add_element(DocumentElement(
                    type=ElementType.HEADING,
                    content=element['content'],
                    level=element['level']
                ))
                
            elif element['type'] == 'list_item':
                current_list_items.append(element['content'])
                
            elif element['type'] == 'paragraph':
                # If there's an ongoing list, flush it
                if current_list_items:
                    self._add_list_element(current_list_items)
                    current_list_items = []
                
                self.structure.add_element(DocumentElement(
                    type=ElementType.PARAGRAPH,
                    content=element['content']
                ))
        
        # Flush any remaining list items
        if current_list_items:
            self._add_list_element(current_list_items)
    
    def _is_heading(self, text: str) -> bool:
        """Detect if text is likely a heading"""
        # Heading heuristics:
        # 1. Short length (typically < 100 chars)
        # 2. No sentence-ending punctuation
        # 3. Starts with common heading patterns
        if len(text) > 100:
            return False
            
        text = text.strip()
        if not text:
            return False
            
        # Check for sentence-ending punctuation
        if text[-1] in {'.', '?', '!'}:
            return False
            
        # Check for heading patterns
        heading_patterns = [
            r'^\d+[\.\)]\s',  # Numbered headings
            r'^[A-Z][^a-z]+$',  # All caps
            r'^(?:Chapter|Section|Part)\s+\d+',  # Common heading starts
            r'^\d+\.\d+\s'  # Hierarchical numbering
        ]
        
        return any(re.match(pattern, text) for pattern in heading_patterns)
    
    def _determine_heading_level(self, text: str) -> int:
        """Determine heading level based on text characteristics"""
        text = text.strip()
        
        # Check for different heading patterns and assign appropriate levels
        if re.match(r'^(?:Chapter|Book)\s+\d+', text, re.I):
            return 1
        elif re.match(r'^(?:Section|Part)\s+\d+', text, re.I):
            return 2
        elif re.match(r'^\d+\.\d+\s', text):
            return 3
        elif re.match(r'^\d+[\.\)]\s', text):
            return 3
        elif text.isupper():
            return 2
        
        return 3  # Default level
    
    def _is_list_item(self, text: str) -> bool:
        """Detect if text is a list item"""
        text = text.strip()
        if not text:
            return False
            
        list_patterns = [
            r'^\s*[\-\*•]\s',  # Bullet points
            r'^\s*\d+[\.\)]\s',  # Numbered items
            r'^\s*[a-z][\.\)]\s',  # Alphabetical items
            r'^\s*\[[xX\s]\]',  # Checkbox items
            r'^\s*[-–—]\s'  # Different types of dashes
        ]
        
        return any(re.match(pattern, text) for pattern in list_patterns)
    
    def _add_list_element(self, items: List[str]) -> None:
        """Add list items to document structure"""
        if not items:
            return
            
        # Determine if list is ordered by checking first item
        first_item = items[0].strip()
        is_ordered = bool(re.match(r'^\s*\d+[\.\)]\s', first_item))
        
        # Clean list items
        cleaned_items = []
        for item in items:
            # Remove list markers
            if is_ordered:
                item = re.sub(r'^\s*\d+[\.\)]\s*', '', item)
            else:
                item = re.sub(r'^\s*(?:[\-\*•]|\[[xX\s]\]|[-–—])\s*', '', item)
            cleaned_items.append(item.strip())
        
        self.structure.add_element(DocumentElement(
            type=ElementType.LIST,
            content=cleaned_items,
            metadata={'ordered': is_ordered}
        ))
    
    def __del__(self):
        """Cleanup temporary files on object destruction"""
        self.file_utils.cleanup_temp_files(self._temp_files)