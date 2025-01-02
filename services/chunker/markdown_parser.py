from typing import List, Dict, Any, Optional
from uuid import uuid4, UUID
import marko
from marko.block import Heading, Paragraph, CodeBlock, List as MarkoList
from marko.inline import RawText, Link, Image
import re
from loguru import logger

from services.chunker.semantic_chunker import SemanticChunker

class MarkdownParser:
    """Parses markdown content into AST and handles chunk creation"""
    
    def __init__(self, max_chunk_size: int = 512, min_chunk_size: int = 128):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.current_path: List[str] = ["root"]
        self.current_level = 0
        self.chunks = []
        self.current_parent_id: Optional[UUID] = None

    def _estimate_tokens(self, text: str) -> int:
        """Rough token count estimation"""
        return len(text.split())

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        return re.sub(r'\s+', ' ', text).strip()

    def _extract_text(self, element: Any) -> str:
        """Recursively extract text from any marko element"""
        if isinstance(element, (str, RawText)):
            return str(element)
        elif isinstance(element, (Link, Image)):
            return element.title or ''
        elif hasattr(element, 'children'):
            if isinstance(element.children, str):
                return element.children
            elif isinstance(element.children, list):
                return ' '.join(self._extract_text(child) for child in element.children)
        return ''

    def _create_chunk(self, content: str, chunk_type: str, 
                     heading: Optional[str] = None,
                     code_language: Optional[str] = None) -> Dict[str, Any]:
        """Create a chunk with metadata"""
        chunk_id = uuid4()
        return {
            "id": chunk_id,
            "content": content,
            "type": chunk_type,
            "hierarchy": {
                "parent_id": self.current_parent_id,
                "level": self.current_level,
                "path": self.current_path.copy()
            },
            "metadata": {
                "heading": heading,
                "code_language": code_language,
                "word_count": len(content.split()) if content else 0,
                "position": len(self.chunks) + 1,
                "type": chunk_type
            }
        }

    def _process_heading(self, element: Heading) -> None:
        """Process heading element and update hierarchy"""
        heading_text = self._extract_text(element)
        heading_text = self._clean_text(heading_text)
        level = element.level

        # Update path and level
        while self.current_level >= level:
            if len(self.current_path) > 1:  # Keep at least "root"
                self.current_path.pop()
            self.current_level -= 1

        self.current_path.append(heading_text)
        self.current_level = level
        self.current_parent_id = uuid4()

        # Create chunk for heading
        self.chunks.append(
            self._create_chunk(
                heading_text,
                "section",
                heading=heading_text
            )
        )

    def _process_list(self, element: MarkoList) -> None:
        """Process list as a single chunk"""
        list_items = []
        for item in element.children:
            item_text = self._extract_text(item)
            if item_text:
                list_items.append(item_text.strip())
        
        if list_items:
            list_text = "\n- " + "\n- ".join(list_items)
            self.chunks.append(
                self._create_chunk(
                    list_text,
                    "list"
                )
            )

    def _process_code_block(self, element: CodeBlock) -> None:
        """Process code block as a single chunk"""
        # CodeBlock children is usually a string
        code_content = str(element.children) if element.children else ""
        self.chunks.append(
            self._create_chunk(
                code_content,
                "code",
                code_language=element.lang
            )
        )

    def _process_paragraph(self, element: Paragraph) -> None:
        """Process paragraph and split if needed"""
        text = self._extract_text(element)
        text = self._clean_text(text)
        
        if not text:  # Skip empty paragraphs
            return
            
        tokens = self._estimate_tokens(text)

        if tokens <= self.max_chunk_size:
            self.chunks.append(
                self._create_chunk(text, "paragraph")
            )
        else:
            # Split into smaller chunks while preserving sentences
            sentences = re.split(r'(?<=[.!?])\s+', text)
            current_chunk = []
            current_tokens = 0

            for sentence in sentences:
                sentence_tokens = self._estimate_tokens(sentence)
                if current_tokens + sentence_tokens > self.max_chunk_size and current_chunk:
                    self.chunks.append(
                        self._create_chunk(
                            " ".join(current_chunk),
                            "paragraph"
                        )
                    )
                    current_chunk = []
                    current_tokens = 0

                current_chunk.append(sentence)
                current_tokens += sentence_tokens

            if current_chunk:
                self.chunks.append(
                    self._create_chunk(
                        " ".join(current_chunk),
                        "paragraph"
                    )
                )

    def parse(self, markdown: str) -> List[Dict[str, Any]]:
        """Parse markdown and return semantic chunks"""
        try:
            doc = marko.parse(markdown)
            self.chunks = []
            self.current_path = ["root"]
            self.current_level = 0
            self.current_parent_id = None

            semantic_chunker = SemanticChunker(
                max_chunk_size=self.max_chunk_size,
                min_chunk_size=self.min_chunk_size
            )

            return semantic_chunker.chunk_content(doc.children)

        except Exception as e:
            logger.error(f"Error parsing markdown: {str(e)}")
            raise