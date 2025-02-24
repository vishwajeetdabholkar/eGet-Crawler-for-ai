from typing import Dict, Any, List
import time
import re
from loguru import logger
from models.chunk_request import ChunkRequest
from models.chunk_response import ChunkResponse, Chunk, ChunkMetadata, ChunkHierarchy
from services.scraper.scraper import WebScraper
from .semantic_chunker import SemanticChunker  # Keeping the original chunker
from uuid import uuid4, UUID

# Import Chonkie's SentenceChunker
from chonkie import SentenceChunker

class ChunkService:
    def __init__(self, scraper: WebScraper):
        self.scraper = scraper
        # Initialize both chunkers
        self.semantic_chunker = SemanticChunker()
        # Initialize Chonkie's SentenceChunker with default parameters
        self.sentence_chunker = SentenceChunker(
            chunk_size=512,  # Default size
            chunk_overlap=50,  # Add some overlap for better context
            return_type="chunks"  # Get full chunk objects
        )
        logger.info("Initialized ChunkService with SemanticChunker and Chonkie SentenceChunker")

    def _clean_markdown(self, markdown_content: str) -> str:
        """
        Clean and normalize markdown content before chunking.
        
        Args:
            markdown_content: Raw markdown content from scraping
            
        Returns:
            Cleaned markdown content
        """
        try:
            # Remove excessive whitespace
            cleaned = re.sub(r'\s+', ' ', markdown_content)
            
            # Fix malformed markdown headers (ensure space after #)
            cleaned = re.sub(r'(#{1,6})([^#\s])', r'\1 \2', cleaned)
            
            # Normalize line breaks
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
            
            # Fix broken list formatting
            cleaned = re.sub(r'(\n\s*)-([^\s])', r'\1- \2', cleaned)
            
            # Remove HTML comments
            cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)
            
            # Remove non-breaking spaces and other special characters
            cleaned = cleaned.replace('&nbsp;', ' ')
            cleaned = cleaned.replace('\xa0', ' ')
            
            # Strip trailing spaces from each line
            cleaned = '\n'.join(line.rstrip() for line in cleaned.split('\n'))
            
            logger.debug(f"Markdown cleaned successfully, size before: {len(markdown_content)}, after: {len(cleaned)}")
            return cleaned
        except Exception as e:
            logger.error(f"Error while cleaning markdown: {str(e)}")
            return markdown_content  # Return original if cleaning fails

    async def process_url(self, request: ChunkRequest) -> ChunkResponse:
        start_time = time.time()
        
        try:
            # Get markdown using existing scraper
            scrape_result = await self.scraper.scrape(
                str(request.url),
                {
                    "only_main": True,
                    "include_raw_html": False,
                    "include_screenshot": False
                }
            )

            if not scrape_result["success"]:
                logger.error("Failed to scrape URL")
                return ChunkResponse(
                    success=False,
                    markdown="",
                    chunks=[],
                    error="Failed to scrape URL"
                )

            markdown_content = scrape_result["data"]["markdown"]
            logger.info(f"Processing markdown content length: {len(markdown_content)}")
            
            # Clean markdown before chunking
            cleaned_markdown = self._clean_markdown(markdown_content)
            
            # Determine which chunker to use based on request parameters or chunk strategy
            if request.chunker_type == "sentence":
                # Use Chonkie's SentenceChunker
                logger.info("Using Chonkie SentenceChunker")
                
                # Configure chunker with request parameters
                self.sentence_chunker = SentenceChunker(
                    chunk_size=request.max_chunk_size or 512,
                    chunk_overlap=request.chunk_overlap or 50,
                    min_sentences_per_chunk=1,
                    min_characters_per_sentence=12
                )
                
                # Get chunks from Chonkie
                chonkie_chunks = self.sentence_chunker.chunk(cleaned_markdown)
                
                # Convert Chonkie chunks to our Chunk format
                chunks = []
                for idx, chonkie_chunk in enumerate(chonkie_chunks):
                    # Create hierarchy (simplified for sentence chunker)
                    hierarchy = ChunkHierarchy(
                        parent_id=None,
                        level=0,
                        path=[]
                    )
                    
                    # Extract sentences info for metadata
                    sentences_info = [s.text for s in chonkie_chunk.sentences]
                    
                    # Create metadata
                    metadata = ChunkMetadata(
                        heading=None,
                        code_language=None,
                        word_count=len(chonkie_chunk.text.split()),
                        position=idx,
                        type="text"
                    )
                    
                    # Create chunk
                    chunk = Chunk(
                        id=uuid4(), # f"sentence-chunk-{idx}",
                        content=chonkie_chunk.text,
                        type="text",
                        hierarchy=hierarchy,
                        metadata=metadata
                    )
                    chunks.append(chunk)
                
                logger.info(f"Generated {len(chunks)} chunks using SentenceChunker")
            else:
                # Use original SemanticChunker (default)
                logger.info("Using SemanticChunker")
                
                # Initialize semantic chunker with request parameters
                semantic_chunker = SemanticChunker(
                    max_chunk_size=request.max_chunk_size or 1500,
                    min_chunk_size=request.min_chunk_size or 200
                )
                
                # Generate chunks using semantic chunker
                chunks_data = semantic_chunker.chunk_markdown(cleaned_markdown)
                logger.info(f"Generated {len(chunks_data)} chunks using SemanticChunker")
                
                # Convert to Pydantic models (same as original code)
                chunks = []
                for chunk_data in chunks_data:
                    try:
                        # Create hierarchy
                        hierarchy = ChunkHierarchy(
                            parent_id=chunk_data["hierarchy"]["parent_id"],
                            level=chunk_data["hierarchy"]["level"],
                            path=chunk_data["hierarchy"]["path"]
                        )
                        
                        # Create metadata
                        metadata = ChunkMetadata(
                            heading=chunk_data["metadata"]["heading"],
                            code_language=chunk_data["metadata"]["code_language"],
                            word_count=chunk_data["metadata"]["word_count"],
                            position=chunk_data["metadata"]["position"],
                            type=chunk_data["metadata"]["type"]
                        )
                        
                        # Create chunk
                        chunk = Chunk(
                            id=chunk_data["id"],
                            content=chunk_data["content"],
                            type=chunk_data["type"],
                            hierarchy=hierarchy,
                            metadata=metadata
                        )
                        chunks.append(chunk)
                    except Exception as e:
                        logger.error(f"Error creating chunk: {str(e)}")
                        logger.error(f"Problematic chunk data: {chunk_data}")
                        continue

            processing_time = time.time() - start_time
            total_words = sum(chunk.metadata.word_count for chunk in chunks)
            avg_chunk_size = total_words / len(chunks) if chunks else 0
            
            logger.info(f"Processed {len(chunks)} chunks in {processing_time:.2f}s")
            
            return ChunkResponse(
                success=True,
                markdown=cleaned_markdown,  # Return cleaned markdown
                chunks=chunks,
                stats={
                    "total_chunks": len(chunks),
                    "avg_chunk_size": avg_chunk_size,
                    "processing_time": processing_time,
                    "chunker_type": request.chunker_type or "semantic"
                }
            )

        except Exception as e:
            logger.error(f"Error processing chunks: {str(e)}")
            return ChunkResponse(
                success=False,
                markdown="",
                chunks=[],
                error=str(e)
            )
