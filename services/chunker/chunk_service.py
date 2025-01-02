from typing import Dict, Any, List
import time
from loguru import logger
from models.chunk_request import ChunkRequest
from models.chunk_response import ChunkResponse, Chunk, ChunkMetadata, ChunkHierarchy
from services.scraper.scraper import WebScraper
from .markdown_parser import MarkdownParser

class ChunkService:
    def __init__(self, scraper: WebScraper):
        self.scraper = scraper

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
                return ChunkResponse(
                    success=False,
                    markdown="",
                    chunks=[],
                    error="Failed to scrape URL"
                )

            markdown_content = scrape_result["data"]["markdown"]
            logger.debug(f"Processing markdown content length: {len(markdown_content)}")

            # Parse markdown into chunks
            parser = MarkdownParser(
                max_chunk_size=request.max_chunk_size,
                min_chunk_size=request.min_chunk_size
            )
            
            chunks_data = parser.parse(markdown_content)
            
            # Convert to Pydantic models explicitly
            chunks: List[Chunk] = []
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

            # Calculate stats
            total_words = sum(chunk.metadata.word_count for chunk in chunks)
            avg_chunk_size = total_words / len(chunks) if chunks else 0
            
            return ChunkResponse(
                success=True,
                markdown=markdown_content,
                chunks=chunks,
                stats={
                    "total_chunks": len(chunks),
                    "avg_chunk_size": avg_chunk_size,
                    "processing_time": time.time() - start_time
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