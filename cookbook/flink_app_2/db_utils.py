# db_utils.py
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pymongo import MongoClient, DESCENDING

from config_utils import load_config

# Configure logging
logger = logging.getLogger("db")

class MongoDBVectorSearch:
    """Handles connection and vector similarity search in MongoDB."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize MongoDB connection with config settings."""
        try:
            self.client = MongoClient(
                config['mongodb_uri'],
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
            # Test the connection
            self.client.admin.command('ping')
            
            self.db = self.client[config['mongodb_database']]
            self.collection = self.db[config['mongodb_collection']]
            
            # Create URLs collection if not exists
            if 'processed_urls' not in self.db.list_collection_names():
                self.db.create_collection('processed_urls')
            
            self.urls_collection = self.db['processed_urls']
            
            logger.info(f"Connected to MongoDB collection: {config['mongodb_collection']}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise

    def vector_search(self, query_embedding: List[float], limit: int = 3, query_text: str = "") -> List[Dict[str, Any]]:
        """Search for similar documents based on vector similarity."""
        try:
            # Create the aggregation pipeline for vector search
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "chunk_content_embedding",
                        "queryVector": query_embedding,
                        "numCandidates": limit * 100,  # Significantly increased candidate pool
                        "limit": limit,  # Get only top 'limit' results
                        "minScore": 0.65  # Adjusted similarity threshold
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "chunk_content": 1,
                        "score": {"$meta": "vectorSearchScore"}
                    }
                }
            ]
            
            # Try standard ANN search first
            results = list(self.collection.aggregate(pipeline))
            
            # If no good results, try exact search (ENN)
            if not results or (results and results[0].get('score', 0) < 0.7):
                logger.info("Low quality ANN results, trying exact search (ENN)")
                exact_pipeline = [
                    {
                        "$vectorSearch": {
                            "index": "vector_index",
                            "path": "chunk_content_embedding",
                            "queryVector": query_embedding,
                            "exact": True,  # Use exact nearest neighbor search
                            "limit": limit  # Maintain the same limit
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "chunk_content": 1,
                            "score": {"$meta": "vectorSearchScore"}
                        }
                    }
                ]
                
                exact_results = list(self.collection.aggregate(exact_pipeline))
                if exact_results and (not results or exact_results[0].get('score', 0) > results[0].get('score', 0)):
                    logger.info("Using exact search results instead of ANN results")
                    results = exact_results
            
            # If still no results, try with more relaxed parameters
            if not results:
                logger.info("No results found, trying with relaxed parameters")
                fallback_pipeline = [
                    {
                        "$vectorSearch": {
                            "index": "vector_index",
                            "path": "chunk_content_embedding",
                            "queryVector": query_embedding,
                            "numCandidates": limit * 200,
                            "limit": limit,  # Still maintain the same limit
                            "minScore": 0.5  # Lower similarity threshold for fallback
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "chunk_content": 1,
                            "score": {"$meta": "vectorSearchScore"}
                        }
                    }
                ]
                results = list(self.collection.aggregate(fallback_pipeline))
            
            # Log detailed information
            logger.info(f"Retrieved {len(results)} documents from vector search")
            if results:
                logger.info(f"Top result score: {results[0].get('score', 'N/A')}")
                for i, result in enumerate(results):
                    score = result.get('score', 'N/A')
                    content_snippet = result.get('chunk_content', '')[:100] + "..."
                    logger.info(f"Result {i+1}: Score={score}, Content={content_snippet}")
            
            # Ensure we're returning only the highest quality results, sorted by score
            sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
            
            # Explicitly limit to the top 'limit' results
            return sorted_results[:limit]
        except Exception as e:
            logger.error(f"Vector search failed: {str(e)}")
            return []
    
# Singleton pattern to ensure one database connection
_mongodb_instance = None

def get_mongodb_instance() -> MongoDBVectorSearch:
    """Get or create MongoDB instance using singleton pattern."""
    global _mongodb_instance
    if _mongodb_instance is None:
        config = load_config()
        _mongodb_instance = MongoDBVectorSearch(config)
    return _mongodb_instance

def store_processed_url(url: str, chunker_type: str, chunk_count: int) -> bool:
    """Store information about a processed URL."""
    try:
        mongo = get_mongodb_instance()
        
        # Create document for the processed URL
        url_doc = {
            "url": url,
            "chunker_type": chunker_type,
            "chunk_count": chunk_count,
            "processed_at": datetime.now()
        }
        
        # Insert or update the URL record
        result = mongo.urls_collection.update_one(
            {"url": url},
            {"$set": url_doc},
            upsert=True
        )
        
        logger.info(f"Stored URL information for {url}")
        return True
    except Exception as e:
        logger.error(f"Failed to store URL information: {str(e)}")
        return False

def get_stored_urls(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve stored URLs ordered by processing time."""
    try:
        mongo = get_mongodb_instance()
        
        # Get URLs sorted by processing time (newest first)
        urls = list(mongo.urls_collection.find(
            {},
            {"_id": 0}
        ).sort("processed_at", DESCENDING).limit(limit))
        
        logger.info(f"Retrieved {len(urls)} processed URLs")
        return urls
    except Exception as e:
        logger.error(f"Failed to retrieve processed URLs: {str(e)}")
        return []