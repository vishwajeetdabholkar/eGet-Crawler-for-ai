from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from uuid import UUID, uuid4
import re
from loguru import logger
import marko
from marko.block import Heading, Paragraph, CodeBlock, List as MarkoList
from marko.inline import RawText, Link, Image

@dataclass
class SemanticSentence:
    text: str
    start_idx: int
    end_idx: int
    token_count: int
    metadata: Dict[str, Any]

@dataclass
class SemanticGroup:
    sentences: List[SemanticSentence]
    heading: Optional[str] = None
    level: int = 0
    parent_id: Optional[UUID] = None

@dataclass
class Section:
    id: UUID
    text: str
    level: int
    content: List[str]
    parent_id: Optional[UUID] = None

class SemanticChunker:
    def __init__(self, 
                 max_chunk_size: int = 1024,
                 min_chunk_size: int = 512,
                 min_sentences_per_chunk: int = 2):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.min_sentences_per_chunk = min_sentences_per_chunk
        
        # Section tracking
        self.current_section: Optional[Section] = None
        self.section_stack: List[Section] = []
        self.pending_content: List[str] = []
        
        # Output management
        self.chunks: List[Dict[str, Any]] = []
        
        # Initialize root section
        root_id = uuid4()
        self.root_section = Section(
            id=root_id,
            text="root",
            level=0,
            content=[],
            parent_id=None
        )
        self.section_stack = [self.root_section]
        self.current_section = self.root_section

    def _clean_raw_text(self, text: str) -> str:
        """Clean RawText and other markers from text"""
        text = re.sub(r'<RawText children=[\'"](.*?)[\'"]>', r'\1', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'^\[|\]$', '', text)
        text = re.sub(r'#\s*$', '', text)
        return text.strip()

    def _extract_text(self, element: Any) -> str:
        """Extract clean text from any marko element"""
        if isinstance(element, (str, RawText)):
            return self._clean_raw_text(str(element))
        elif isinstance(element, (Link, Image)):
            return element.title or ''
        elif hasattr(element, 'children'):
            if isinstance(element.children, str):
                return self._clean_raw_text(element.children)
            elif isinstance(element.children, list):
                return ' '.join(self._extract_text(child) for child in element.children)
        return ''

    def _estimate_tokens(self, text: str) -> int:
        return len(text.split())

    def _get_section_path(self) -> List[str]:
        """Get current section path"""
        return [section.text for section in self.section_stack]

    def _create_chunk(self, content: List[str], chunk_type: str) -> Dict[str, Any]:
        """Create a chunk with proper hierarchy and metadata"""
        clean_content = ' '.join(self._clean_raw_text(text) for text in content)
        chunk_id = uuid4()
        
        return {
            "id": chunk_id,
            "content": clean_content,
            "type": chunk_type,
            "hierarchy": {
                "parent_id": self.current_section.parent_id if self.current_section else None,
                "level": self.current_section.level if self.current_section else 0,
                "path": self._get_section_path()
            },
            "metadata": {
                "heading": self.current_section.text if self.current_section else None,
                "code_language": None,
                "word_count": self._estimate_tokens(clean_content),
                "position": len(self.chunks) + 1,
                "type": chunk_type,
                "sentence_count": len(content)
            }
        }

    def _flush_pending_content(self) -> None:
        """Create chunk from pending content"""
        if not self.pending_content:
            return

        combined_text = ' '.join(self.pending_content)
        if self._estimate_tokens(combined_text) > 0:
            chunk = self._create_chunk(self.pending_content, "section")
            self.chunks.append(chunk)
        self.pending_content = []

    def _process_heading(self, element: Heading) -> None:
        """Process heading with semantic context"""
        # Flush any pending content before changing section
        self._flush_pending_content()
        
        heading_text = self._extract_text(element)
        level = element.level

        # Pop sections of same or higher level
        while self.section_stack and self.section_stack[-1].level >= level:
            self.section_stack.pop()

        # Create new section
        new_section = Section(
            id=uuid4(),
            text=heading_text,
            level=level,
            content=[],
            parent_id=self.section_stack[-1].id if self.section_stack else None
        )
        
        self.section_stack.append(new_section)
        self.current_section = new_section
        
        # Add heading to pending content
        self.pending_content.append(heading_text)

    def _process_content(self, text: str, content_type: str = "paragraph") -> None:
        """Process content under current section"""
        clean_text = self._clean_raw_text(text)
        
        if not clean_text:
            return
            
        current_tokens = sum(self._estimate_tokens(t) for t in self.pending_content)
        new_tokens = self._estimate_tokens(clean_text)
        
        if current_tokens + new_tokens > self.max_chunk_size:
            self._flush_pending_content()
            
        self.pending_content.append(clean_text)

    def _process_code_block(self, element: CodeBlock) -> None:
        """Process code block as separate chunk but maintain context"""
        self._flush_pending_content()  # Flush any pending content
        
        code_content = self._extract_text(element)
        if not code_content:
            return
            
        chunk = self._create_chunk([code_content], "code")
        chunk["metadata"]["code_language"] = element.lang if hasattr(element, 'lang') else None
        self.chunks.append(chunk)

    def _process_list(self, element: MarkoList) -> None:
        """Process list with context"""
        self._flush_pending_content()
        
        list_items = []
        for item in element.children:
            item_text = self._extract_text(item)
            if item_text:
                list_items.append(item_text)

        if list_items:
            list_text = "\n- " + "\n- ".join(list_items)
            chunk = self._create_chunk([list_text], "list")
            chunk["metadata"]["sentence_count"] = len(list_items)
            self.chunks.append(chunk)

    def chunk_content(self, elements: List[Any]) -> List[Dict[str, Any]]:
        """Process content preserving semantic relationships"""
        self.chunks = []
        self.pending_content = []
        self.section_stack = [self.root_section]
        self.current_section = self.root_section

        try:
            for element in elements:
                if isinstance(element, Heading):
                    self._process_heading(element)
                elif isinstance(element, CodeBlock):
                    self._process_code_block(element)
                elif isinstance(element, MarkoList):
                    self._process_list(element)
                elif isinstance(element, Paragraph):
                    paragraph_text = self._extract_text(element)
                    self._process_content(paragraph_text, "paragraph")
                    
            # Flush any remaining content
            self._flush_pending_content()
            
            return self.chunks
            
        except Exception as e:
            logger.error(f"Error in chunk_content: {str(e)}")
            raise