import re
from typing import Dict, Any, List, Tuple, Optional
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.table import _Cell, Table
from docx.shared import Pt, RGBColor
import base64
from io import BytesIO
from loguru import logger

from ..base_converter import BaseDocumentConverter, ConversionContext
from ..document_structure import DocumentStructure, DocumentElement, ElementType
from ..file_utils import FileUtils
from models.file_conversion_models import FileMetadata, FileType

class DocxConverter(BaseDocumentConverter):
    """Enhanced DOCX to Markdown converter with style preservation"""
    
    def __init__(self):
        super().__init__()
        self.structure = DocumentStructure()
        self.file_utils = FileUtils()
        self._temp_files = []
        self._image_counter = 0
        self._current_list_id = None
        self._current_list_level = 0
        self._list_stack = []
        
    async def convert(self, content: bytes, context: ConversionContext) -> Tuple[str, FileMetadata]:
        """Convert DOCX file to markdown"""
        self.context = context
        temp_path = None
        
        try:
            # Create temporary file
            temp_path = self.file_utils.create_temp_file(content, '.docx')
            self._temp_files.append(temp_path)
            
            # Load document
            doc = Document(temp_path)
            
            # Process document metadata
            self._add_document_metadata(doc)
            
            # Initialize counters for metadata
            images_count = 0
            tables_count = 0
            equations_count = 0
            
            # Process content
            for element in doc.element.body:
                if isinstance(element, CT_P):
                    # Process paragraph
                    paragraph = Paragraph(element, doc)
                    if 'math' in paragraph._element.xml:
                        equations_count += 1
                    self._process_paragraph(paragraph)
                    
                elif isinstance(element, CT_Tbl):
                    # Process table
                    table = Table(element, doc)
                    self._process_table(table)
                    tables_count += 1
            
            # Process images from all sources
            images_count = self._process_images(doc)
            
            # Convert to markdown
            markdown_content = self.structure.to_markdown()
            
            # Create metadata
            metadata = FileMetadata(
                filename=context.filename,
                size_bytes=context.size_bytes,
                file_type=FileType.DOCX,
                pages=len(doc.sections),
                images_count=images_count,
                tables_count=tables_count,
                equations_count=equations_count
            )
            
            return markdown_content, metadata
            
        except Exception as e:
            logger.error(f"DOCX conversion error: {str(e)}")
            raise
        finally:
            # Cleanup temporary files
            self.file_utils.cleanup_temp_files(self._temp_files)
    
    def _add_document_metadata(self, doc: Document) -> None:
        """Add document metadata to structure"""
        try:
            if doc.core_properties:
                metadata = {
                    'title': doc.core_properties.title,
                    'author': doc.core_properties.author,
                    'comments': doc.core_properties.comments,
                    'category': doc.core_properties.category,
                    'created': doc.core_properties.created.isoformat() if doc.core_properties.created else None,
                    'modified': doc.core_properties.modified.isoformat() if doc.core_properties.modified else None,
                    'last_modified_by': doc.core_properties.last_modified_by,
                    'revision': doc.core_properties.revision,
                    'keywords': doc.core_properties.keywords,
                    'subject': doc.core_properties.subject
                }
                
                # Filter out None values
                metadata = {k: v for k, v in metadata.items() if v is not None}
                
                self.structure.add_element(DocumentElement(
                    type=ElementType.METADATA,
                    content=metadata,
                    metadata={'source': 'document_properties'}
                ))
                
        except Exception as e:
            self.log_warning(f"Error extracting document metadata: {str(e)}")
    
    def _process_paragraph(self, paragraph: Paragraph) -> None:
        """Process paragraph with style preservation"""
        if not paragraph.text.strip():
            return
            
        # Get paragraph style
        style_name = paragraph.style.name if paragraph.style else 'Normal'
        
        # Check for headings
        if style_name.startswith('Heading'):
            try:
                level = int(style_name[-1])
                self.structure.add_element(DocumentElement(
                    type=ElementType.HEADING,
                    content=paragraph.text,
                    level=level,
                    metadata=self._get_paragraph_style_info(paragraph)
                ))
                return
            except ValueError:
                pass
        
        # Check for lists
        list_info = self._get_list_info(paragraph)
        if list_info:
            self._handle_list_item(paragraph, list_info)
            return
        
        # Handle regular paragraph
        self._handle_regular_paragraph(paragraph)
    
    def _get_paragraph_style_info(self, paragraph: Paragraph) -> Dict[str, Any]:
        """Extract detailed paragraph style information"""
        style_info = {
            'name': paragraph.style.name if paragraph.style else 'Normal',
            'alignment': str(paragraph.alignment) if hasattr(paragraph, 'alignment') else None,
            'indentation': {},
            'spacing': {},
            'font': {}
        }
        
        try:
            if paragraph._element.pPr is not None:
                # Get indentation
                if paragraph._element.pPr.ind is not None:
                    ind = paragraph._element.pPr.ind
                    style_info['indentation'].update({
                        'left': ind.left.__str__() if ind.left else None,
                        'right': ind.right.__str__() if ind.right else None,
                        'first_line': ind.firstLine.__str__() if ind.firstLine else None,
                    })
                
                # Get spacing
                if paragraph._element.pPr.spacing is not None:
                    spacing = paragraph._element.pPr.spacing
                    style_info['spacing'].update({
                        'before': spacing.before.__str__() if spacing.before else None,
                        'after': spacing.after.__str__() if spacing.after else None,
                        'line': spacing.line.__str__() if spacing.line else None,
                    })
                
            # Get run properties for first run (font info)
            if paragraph.runs:
                run = paragraph.runs[0]
                font = run.font
                style_info['font'].update({
                    'name': font.name,
                    'size': str(font.size) if font.size else None,
                    'bold': font.bold,
                    'italic': font.italic,
                    'underline': font.underline,
                    'color': str(font.color.rgb) if font.color and font.color.rgb else None
                })
        
        except Exception as e:
            self.log_warning(f"Error extracting paragraph style: {str(e)}")
        
        return style_info
    
    def _get_list_info(self, paragraph: Paragraph) -> Optional[Dict[str, Any]]:
        """Extract list information from paragraph"""
        try:
            if paragraph._element.pPr is None:
                return None
                
            num_pr = paragraph._element.pPr.xpath('./w:numPr')
            if not num_pr:
                return None
                
            num_pr = num_pr[0]
            ilvl = num_pr.xpath('./w:ilvl/@w:val')
            numId = num_pr.xpath('./w:numId/@w:val')
            
            if ilvl and numId:
                return {
                    'level': int(ilvl[0]),
                    'list_id': numId[0],
                    'is_ordered': self._is_ordered_list(paragraph)
                }
                
        except Exception as e:
            self.log_warning(f"Error getting list info: {str(e)}")
        
        return None
    
    def _is_ordered_list(self, paragraph: Paragraph) -> bool:
        """Determine if paragraph is part of an ordered list"""
        try:
            # Check numbering properties
            if paragraph._element.pPr is not None:
                num_pr = paragraph._element.pPr.xpath('./w:numPr')
                if num_pr:
                    num_id = num_pr[0].xpath('./w:numId/@w:val')
                    if num_id:
                        # Could extend this to check actual numbering definition
                        # For now, assume basic heuristic
                        text = paragraph.text.strip()
                        return bool(re.match(r'^\d+\.?\s', text))
        except Exception:
            pass
        return False
    
    def _handle_list_item(self, paragraph: Paragraph, list_info: Dict[str, Any]) -> None:
        """Handle list item paragraph"""
        list_id = list_info['list_id']
        level = list_info['level']
        is_ordered = list_info['is_ordered']
        
        # Handle list state changes
        if self._current_list_id != list_id:
            # Close any open lists
            self._close_current_list()
            self._current_list_id = list_id
            self._list_stack = []
        
        # Adjust list stack for current level
        while self._list_stack and self._list_stack[-1]['level'] >= level:
            self._list_stack.pop()
        
        # Create new list if needed
        if not self._list_stack or self._list_stack[-1]['level'] < level:
            self._list_stack.append({
                'level': level,
                'ordered': is_ordered,
                'items': []
            })
        
        # Add item to current list
        self._list_stack[-1]['items'].append(paragraph.text.strip())
    
    def _close_current_list(self) -> None:
        """Close current list and add to structure"""
        if self._list_stack:
            for list_info in self._list_stack:
                self.structure.add_element(DocumentElement(
                    type=ElementType.LIST,
                    content=list_info['items'],
                    metadata={
                        'ordered': list_info['ordered'],
                        'level': list_info['level']
                    }
                ))
            
            self._list_stack = []
            self._current_list_id = None
    
    def _handle_regular_paragraph(self, paragraph: Paragraph) -> None:
        """Handle regular paragraph content"""
        # Close any open lists
        self._close_current_list()
        
        # Process runs to preserve inline formatting
        formatted_content = []
        for run in paragraph.runs:
            text = run.text
            if not text.strip():
                continue
                
            # Apply inline formatting
            if run.bold:
                text = f"**{text}**"
            if run.italic:
                text = f"*{text}*"
            if run.underline:
                text = f"__{text}__"
                
            formatted_content.append(text)
        
        if formatted_content:
            self.structure.add_element(DocumentElement(
                type=ElementType.PARAGRAPH,
                content=''.join(formatted_content),
                metadata=self._get_paragraph_style_info(paragraph)
            ))
    
    def _process_table(self, table: Table) -> None:
        """Process table with formatting preservation"""
        table_data = []
        
        for row_idx, row in enumerate(table.rows):
            row_data = []
            for cell in row.cells:
                # Get cell text and clean it
                cell_text = ' '.join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                row_data.append(cell_text)
            table_data.append(row_data)
        
        if table_data:
            self.structure.add_element(DocumentElement(
                type=ElementType.TABLE,
                content=table_data,
                metadata={
                    'has_header': True,  # Assume first row is header
                    'style': self._get_table_style(table)
                }
            ))
    
    def _get_table_style(self, table: Table) -> Dict[str, Any]:
        """Extract table style information"""
        style_info = {
            'borders': {},
            'alignment': '',
            'width': str(table.table.width) if hasattr(table.table, 'width') else None
        }
        
        try:
            if table._element.tblPr is not None:
                # Get borders
                borders = table._element.tblPr.xpath('./w:tblBorders')
                if borders:
                    for border in borders[0]:
                        style_info['borders'][border.tag.split('}')[-1]] = {
                            'size': border.get(qn('w:sz')),
                            'color': border.get(qn('w:color')),
                            'style': border.get(qn('w:val'))
                        }
                
                # Get alignment
                jc = table._element.tblPr.xpath('./w:jc')
                if jc:
                    style_info['alignment'] = jc[0].get(qn('w:val'))
                    
        except Exception as e:
            self.log_warning(f"Error getting table style: {str(e)}")
            
        return style_info
    
    def _process_images(self, doc: Document) -> int:
        """Process all images in document"""
        image_count = 0
        
        try:
            # Process inline shapes
            for shape in doc.inline_shapes:
                if self._process_inline_shape(shape):
                    image_count += 1
            
            # Process shapes
            for shape in doc.element.body.xpath('//w:drawing'):
                if self._process_shape(shape):
                    image_count += 1
                    
        except Exception as e:
            self.log_warning(f"Error processing images: {str(e)}")
            
        return image_count
    
    def _process_inline_shape(self, shape) -> bool:
        """Process inline shape"""
        try:
            if shape.type == 3:  # Picture
                image_part = shape._inline.graphic.graphicData.pic.blipFill.blip.embed
                image_data = shape.part.related_parts[image_part].image.blob
                
                if image_data and self.file_utils.is_valid_image(image_data):
                    self._image_counter += 1
                    encoded_image = self.file_utils.encode_image(image_data)
                    
                    if encoded_image:
                        self.structure.add_element(DocumentElement(
                            type=ElementType.IMAGE,
                            content=encoded_image,
                            metadata={
                                'width': shape.width,
                                'height': shape.height,
                                'image_number': self._image_counter,
                                'alt_text': self._get_shape_alt_text(shape)
                            }
                        ))
                        return True
        except Exception as e:
            self.log_warning(f"Error processing inline shape: {str(e)}")
        return False

    def _process_shape(self, shape) -> bool:
        """Process regular shape"""
        try:
            # Extract image data from shape
            inline = shape.xpath('.//wp:inline', namespaces={'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'})
            if inline:
                blip = shape.xpath('.//a:blip/@r:embed', namespaces={
                    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
                    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
                })
                
                if blip:
                    image_part = blip[0]
                    try:
                        # Get image data from relationship
                        image_part = shape.getparent().part.related_parts[image_part]
                        image_data = image_part.blob
                        
                        if image_data and self.file_utils.is_valid_image(image_data):
                            self._image_counter += 1
                            encoded_image = self.file_utils.encode_image(image_data)
                            
                            if encoded_image:
                                # Get shape dimensions
                                extent = inline[0].xpath('.//wp:extent', namespaces={'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'})
                                width = int(extent[0].get('cx')) if extent else None
                                height = int(extent[0].get('cy')) if extent else None
                                
                                self.structure.add_element(DocumentElement(
                                    type=ElementType.IMAGE,
                                    content=encoded_image,
                                    metadata={
                                        'width': width,
                                        'height': height,
                                        'image_number': self._image_counter,
                                        'alt_text': self._get_shape_alt_text(shape)
                                    }
                                ))
                                return True
                    except KeyError:
                        self.log_warning(f"Image relationship {image_part} not found")
        except Exception as e:
            self.log_warning(f"Error processing shape: {str(e)}")
        return False

    def _get_shape_alt_text(self, shape) -> str:
        """Extract alternative text from shape"""
        try:
            # Try to get alt text from different possible locations
            alt_text = None
            
            # For inline shapes
            if hasattr(shape, 'inline'):
                docPr = shape.inline.docPr
                if docPr is not None:
                    alt_text = docPr.get('descr') or docPr.get('title')
            
            # For regular shapes
            elif hasattr(shape, 'xpath'):
                # Try docPr
                doc_pr = shape.xpath('.//wp:docPr', namespaces={'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'})
                if doc_pr:
                    alt_text = doc_pr[0].get('descr') or doc_pr[0].get('title')
                
                # Try pic:cNvPr
                if not alt_text:
                    cnv_pr = shape.xpath('.//pic:cNvPr', namespaces={'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture'})
                    if cnv_pr:
                        alt_text = cnv_pr[0].get('descr') or cnv_pr[0].get('title')
            
            return alt_text or f"Image {self._image_counter}"
            
        except Exception as e:
            self.log_warning(f"Error getting shape alt text: {str(e)}")
            return f"Image {self._image_counter}"

    def __del__(self):
        """Cleanup temporary files on object destruction"""
        self.file_utils.cleanup_temp_files(self._temp_files)