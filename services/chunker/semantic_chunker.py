from typing import List, Dict, Any, Optional, Tuple
from uuid import uuid4
import re
from loguru import logger

class SemanticChunker:
    """Semantic markdown chunker"""
    
    def __init__(self, 
                 max_chunk_size: int = 1500,
                 min_chunk_size: int = 200):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        # Default header patterns
        self.headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
            ("####", "Header 4"),
            ("#####", "Header 5"),
            ("######", "Header 6")
        ]
        logger.info("Initialized SemanticChunker")

    def chunk_markdown(self, text: str) -> List[Dict[str, Any]]:
        """Split markdown into semantic chunks"""
        try:
            chunks = []
            lines = text.split('\n')
            current_content: List[str] = []
            current_metadata: Dict[str, str] = {}
            header_stack: List[Dict[str, Any]] = []
            initial_metadata: Dict[str, str] = {}

            # Track code blocks
            in_code_block = False
            code_fence = ""
            code_language = None
            
            for line in lines:
                stripped_line = line.strip()

                # Handle code blocks
                if not in_code_block and stripped_line.startswith('```'):
                    in_code_block = True
                    code_fence = '```'
                    code_language = stripped_line[3:].strip()
                    current_content.append(line)
                    continue
                elif in_code_block:
                    current_content.append(line)
                    if stripped_line.startswith(code_fence):
                        in_code_block = False
                        # Create code chunk
                        if current_content:
                            chunk = self._create_chunk(
                                content='\n'.join(current_content),
                                metadata=current_metadata.copy(),
                                chunk_type="code",
                                code_language=code_language
                            )
                            if chunk:
                                chunks.append(chunk)
                            current_content = []
                    continue

                # Check for headers
                header_match = False
                for sep, name in self.headers_to_split_on:
                    if stripped_line.startswith(sep + " "):
                        header_match = True
                        
                        # Save previous content if exists
                        if current_content:
                            chunk = self._create_chunk(
                                content='\n'.join(current_content),
                                metadata=current_metadata.copy()
                            )
                            if chunk:
                                chunks.append(chunk)
                            current_content = []

                        # Get header level and content
                        level = len(sep)
                        header_text = stripped_line[len(sep):].strip()

                        # Update header stack and metadata
                        while header_stack and header_stack[-1]["level"] >= level:
                            popped = header_stack.pop()
                            if popped["name"] in initial_metadata:
                                initial_metadata.pop(popped["name"])

                        header_info = {
                            "level": level,
                            "name": name,
                            "text": header_text
                        }
                        header_stack.append(header_info)
                        initial_metadata[name] = header_text

                        # Start new section
                        current_metadata = initial_metadata.copy()
                        current_content = [line]
                        break

                if not header_match and not in_code_block:
                    if line.strip() or current_content:
                        current_content.append(line)
                    elif current_content:
                        # Create chunk for accumulated content
                        chunk = self._create_chunk(
                            content='\n'.join(current_content),
                            metadata=current_metadata.copy()
                        )
                        if chunk:
                            chunks.append(chunk)
                        current_content = []

            # Handle remaining content
            if current_content:
                chunk = self._create_chunk(
                    content='\n'.join(current_content),
                    metadata=current_metadata.copy()
                )
                if chunk:
                    chunks.append(chunk)

            # Update positions
            for i, chunk in enumerate(chunks):
                chunk["metadata"]["position"] = i

            logger.info(f"Created {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"Error chunking markdown: {str(e)}")
            return []

    def _create_chunk(self,
                     content: str,
                     metadata: Dict[str, str],
                     chunk_type: str = "text",
                     code_language: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create a chunk with proper metadata"""
        try:
            # Clean content
            content = content.strip()
            if not content:
                return None

            # Get word count
            word_count = len(content.split())
            if word_count < self.min_chunk_size and chunk_type != "code":
                return None

            # Build header path
            path = []
            for i in range(1, 7):
                header_key = f"Header {i}"
                if header_key in metadata:
                    path.append(metadata[header_key])

            # Create chunk
            return {
                "id": str(uuid4()),
                "content": content,
                "type": chunk_type,
                "hierarchy": {
                    "parent_id": None,  # Set by the caller if needed
                    "level": len(path),
                    "path": path
                },
                "metadata": {
                    "headers": {k: v for k, v in metadata.items() if k.startswith("Header")},
                    "heading": metadata.get(f"Header {len(path)}" if path else None),
                    "code_language": code_language,
                    "word_count": word_count,
                    "position": 0,  # Updated later
                    "type": chunk_type
                }
            }
        except Exception as e:
            logger.error(f"Error creating chunk: {str(e)}")
            return None