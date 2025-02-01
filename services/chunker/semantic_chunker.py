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
        try:
            chunks = []
            lines = text.split('\n')
            current_content: List[str] = []
            current_metadata: Dict[str, str] = {}
            header_stack: List[Dict[str, Any]] = []
            initial_metadata: Dict[str, str] = {}
            
            # Add handling for content before first header
            preamble_content = []
            found_first_header = False

            # Track code blocks
            in_code_block = False
            code_fence = ""
            code_language = None
            
            for line in lines:
                stripped_line = line.strip()

                # Handle content before first header
                if not found_first_header and not any(sep + " " in stripped_line for sep, _ in self.headers_to_split_on):
                    preamble_content.append(line)
                    continue

                # Handle code blocks first
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
                        found_first_header = True
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
                        elif preamble_content and not chunks:  # Handle preamble content
                            chunk = self._create_chunk(
                                content='\n'.join(preamble_content),
                                metadata={"type": "preamble"}
                            )
                            if chunk:
                                chunks.append(chunk)
                            preamble_content = []

                        # Rest of the header handling code...
                        
                if not header_match and not in_code_block:
                    if line.strip() or current_content:
                        current_content.append(line)
                    elif current_content:
                        chunk = self._create_chunk(
                            content='\n'.join(current_content),
                            metadata=current_metadata.copy()
                        )
                        if chunk:
                            chunks.append(chunk)
                        current_content = []

            # Handle any remaining content
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

            return chunks

        except Exception as e:
            logger.error(f"Error chunking markdown: {str(e)}")
            return []

    def _create_chunk(self,
                 content: str,  
                 metadata: Dict[str, str],
                 chunk_type: str = "text",
                 code_language: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create a chunk with proper metadata and smart size handling.
        
        Args:
            content: The text content for the chunk
            metadata: Dictionary of metadata about the chunk
            chunk_type: Type of chunk ('text', 'code', etc)
            code_language: Programming language for code chunks
        
        Returns:
            Dictionary containing the chunk data or None if invalid
        """
        try:
            # Basic content validation
            if not content or not isinstance(content, str):
                return None
                
            # Clean whitespace while preserving meaningful line breaks
            content = "\n".join(line.rstrip() for line in content.splitlines()).strip()
            if not content:
                return None

            # Calculate metrics
            lines = content.splitlines()
            word_count = len(content.split())
            is_header_chunk = any(key.startswith("Header") for key in metadata)
            is_code_chunk = chunk_type == "code"
            is_preamble = metadata.get("type") == "preamble"
            
            # Smart size handling:
            # 1. Always keep headers regardless of size
            # 2. Always keep code blocks intact
            # 3. Keep preambles unless extremely small
            # 4. Be flexible with size constraints for meaningful content
            if not (is_header_chunk or is_code_chunk or is_preamble):
                if word_count < self.min_chunk_size:
                    # For very small chunks, try to combine with next section
                    # but don't discard them entirely
                    metadata["needs_merge"] = True
                elif word_count > self.max_chunk_size:
                    # For large chunks, we'll keep them but flag for potential splitting
                    metadata["needs_split"] = True
                    logger.warning(f"Chunk exceeds max size: {word_count} words")

            # Build header path - helps maintain document hierarchy
            path = []
            for i in range(1, 7):
                header_key = f"Header {i}"
                if header_key in metadata:
                    path.append(metadata[header_key])

            # Determine chunk type heuristically if not specified
            if chunk_type == "text":
                if content.startswith("#"):
                    chunk_type = "header"
                elif content.startswith("```"):
                    chunk_type = "code"
                elif content.startswith("- ") or content.startswith("* ") or content.startswith("1. "):
                    chunk_type = "list"
                elif "|" in content and "-|-" in content:
                    chunk_type = "table"
                    
            # Enhanced metadata
            enhanced_metadata = {
                "headers": {k: v for k, v in metadata.items() if k.startswith("Header")},
                "heading": metadata.get(f"Header {len(path)}" if path else None),
                "code_language": code_language if is_code_chunk else None,
                "word_count": word_count,
                "line_count": len(lines),
                "position": metadata.get("position", 0),
                "type": chunk_type,
                "content_preview": content[:100] + "..." if len(content) > 100 else content,
                # Semantic indicators
                "has_code": "```" in content or "`" in content,
                "has_lists": bool(re.search(r'^\s*[-*]\s', content, re.MULTILINE)),
                "has_links": "[" in content and "](" in content,
                "estimated_read_time": max(1, word_count // 200)  # minutes, assuming 200wpm
            }

            # Create the final chunk
            chunk = {
                "id": str(uuid4()),
                "content": content,
                "type": chunk_type,
                "hierarchy": {
                    "parent_id": metadata.get("parent_id"),
                    "level": len(path),
                    "path": path
                },
                "metadata": enhanced_metadata
            }

            # Log chunk creation for debugging
            logger.debug(f"Created chunk: type={chunk_type}, words={word_count}, " 
                        f"level={len(path)}, content_preview={content[:50]}...")

            return chunk

        except Exception as e:
            logger.error(f"Error creating chunk: {str(e)}")
            logger.error(f"Problematic content preview: {content[:100] if content else 'None'}")
            return None
