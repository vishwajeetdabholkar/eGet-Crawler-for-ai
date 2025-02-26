# kafka_utils.py
import json
import logging
import asyncio
import httpx
from uuid import uuid4
from typing import Dict, Any, List, Optional

from confluent_kafka import Producer
from confluent_kafka.serialization import StringSerializer, SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer

# Configure logging
logger = logging.getLogger("kafka")

# The combined schema for Avro serialization
AVRO_SCHEMA = """
{
"doc": "Schema for website content chunks processed for RAG applications.",
"fields": [
    {
    "doc": "Unique identifier for the chunk.",
    "name": "chunk_id",
    "type": "string"
    },
    {
    "doc": "Source URL where the content was extracted from.",
    "name": "url",
    "type": "string"
    },
    {
    "doc": "Position of this chunk in the sequence of chunks from the source.",
    "name": "chunk_number",
    "type": "int"
    },
    {
    "doc": "Total number of chunks extracted from the source URL.",
    "name": "total_chunks",
    "type": "int"
    },
    {
    "doc": "The actual text content of the chunk.",
    "name": "chunk_content",
    "type": "string"
    },
    {
    "doc": "Type of the chunk (text, code, header, list, etc.).",
    "name": "chunk_type",
    "type": "string"
    },
    {
    "doc": "ISO datetime when the chunk was processed.",
    "name": "timestamp",
    "type": "string"
    },
    {
    "doc": "Number of words in the chunk content.",
    "name": "word_count",
    "type": "int"
    },
    {
    "default": null,
    "doc": "Programming language if this is a code chunk.",
    "name": "code_language",
    "type": [
        "null",
        "string"
    ]
    },
    {
    "doc": "Original position in the document.",
    "name": "position",
    "type": "int"
    },
    {
    "doc": "Semantic type of content (section, paragraph, code, list, table).",
    "name": "content_type",
    "type": "string"
    },
    {
    "default": null,
    "doc": "Associated heading for this chunk if available.",
    "name": "heading",
    "type": [
        "null",
        "string"
    ]
    }
],
"name": "WebsiteChunk",
"namespace": "io.eget.chunks",
"type": "record"
}
"""

class KafkaService:
    """Service to manage Kafka producer and sending data to Kafka."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Kafka service with config."""
        self.config = config
        self.producer = self._create_kafka_producer()
        self.topic = config.get("kafka_topic", "website_chunks")
        
        logger.info(f"Kafka service initialized with topic: {self.topic}")
    
    def _create_kafka_producer(self) -> Producer:
        """Create Kafka producer with config settings."""
        kafka_config = {
            'bootstrap.servers': self.config.get("kafka_bootstrap_servers"),
            'security.protocol': 'SASL_SSL',
            'sasl.mechanisms': 'PLAIN',
            'sasl.username': self.config.get("kafka_api_key"),
            'sasl.password': self.config.get("kafka_api_secret"),
            'client.id': 'scraper-chunker-client'
        }
        
        try:
            # Initialize Schema Registry client
            schema_registry_conf = {
                'url': self.config.get("schema_registry_url"),
                'basic.auth.user.info': f"{self.config.get('schema_registry_api_key')}:{self.config.get('schema_registry_api_secret')}"
            }
            self.schema_registry_client = SchemaRegistryClient(schema_registry_conf)
            
            # Create serializers
            self.string_serializer = StringSerializer('utf_8')
            self.avro_serializer = AvroSerializer(
                self.schema_registry_client,
                AVRO_SCHEMA,
                lambda message, ctx: message
            )
            
            producer = Producer(kafka_config)
            logger.info("Kafka producer initialized with Avro serialization")
            return producer
        except Exception as e:
            logger.error(f"Failed to create Kafka producer: {str(e)}")
            raise RuntimeError(f"Kafka producer initialization failed: {str(e)}")
    
    def _delivery_report(self, err, msg):
        """Delivery callback for Kafka producer."""
        if err is not None:
            logger.error(f'Message delivery failed: {err}')
        else:
            logger.debug(f'Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}')
    
    def send_message(self, key: str, value: Dict[str, Any]) -> None:
        """Send a message to Kafka."""
        try:
            self.producer.produce(
                topic=self.topic,
                key=self.string_serializer(key),
                value=self.avro_serializer(
                    value, 
                    SerializationContext(self.topic, MessageField.VALUE)
                ),
                on_delivery=self._delivery_report
            )
            # Trigger delivery callbacks
            self.producer.poll(0)
            
        except Exception as e:
            logger.error(f"Error sending message to Kafka: {str(e)}")
    
    def flush(self, timeout: int = 10) -> int:
        """Flush all messages and return the number of messages still in queue."""
        return self.producer.flush(timeout)

async def fetch_and_chunk_url(url: str, chunker_api_url: str, chunker_type: str = "sentence") -> Optional[Dict[str, Any]]:
    """Fetch and chunk content from a URL using the chunker API."""
    try:
        logger.info(f"Processing URL: {url}")
        
        # Prepare chunker API request
        payload = {
            "url": url,
            "max_chunk_size": 512,
            "min_chunk_size": 128,
            "preserve_code_blocks": True,
            "include_metadata": True,
            "chunker_type": chunker_type,
            "chunk_overlap": 50
        }
        
        # Call chunker API
        async with httpx.AsyncClient() as client:
            response = await client.post(chunker_api_url, json=payload, timeout=120.0)
            response.raise_for_status()
            result = response.json()
            
            if not result.get("success"):
                logger.error(f"API error for {url}: {result.get('error')}")
                return None
            
            logger.info(f"Successfully processed {url}")
            return result
                
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error for {url}: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error for {url}: {str(e)}")
    except Exception as e:
        logger.error(f"Error processing {url}: {str(e)}", exc_info=True)
    
    return None

async def process_url_and_send_to_kafka(url: str, config: Dict[str, Any], chunker_type: str = "sentence") -> Dict[str, Any]:
    """Process URL, chunk it, and send chunks to Kafka."""
    try:
        # Initialize Kafka service
        kafka_service = KafkaService(config)
        
        # Process URL through chunker API
        result = await fetch_and_chunk_url(url, config.get("chunker_api_url"), chunker_type)
        
        if not result or not result.get("success"):
            error_msg = result.get("error", "Unknown error") if result else "Unknown error"
            return {"success": False, "error": error_msg}
        
        # Extract chunks
        chunks = result.get("chunks", [])
        if not chunks:
            return {"success": True, "chunks": [], "message": "No chunks found"}
        
        logger.info(f"Sending {len(chunks)} chunks to Kafka topic: {kafka_service.topic}")
        
        # Process each chunk and send to Kafka
        for i, chunk in enumerate(chunks):
            # Create message structure
            message = {
                "chunk_id": str(chunk.get("id", str(uuid4()))),
                "url": url,
                "chunk_number": i + 1,
                "total_chunks": len(chunks),
                "chunk_content": chunk.get("content", ""),
                "chunk_type": chunk.get("type", "text"),
                "timestamp": str(result.get("processed_at", "")),
                
                # Flatten metadata fields
                "word_count": chunk.get("metadata", {}).get("word_count", 0),
                "position": chunk.get("metadata", {}).get("position", 0),
                "content_type": chunk.get("metadata", {}).get("type", "text"),
                "heading": chunk.get("metadata", {}).get("heading"),
                "code_language": chunk.get("metadata", {}).get("code_language")
            }
            
            # Send to Kafka
            kafka_service.send_message(message["chunk_id"], message)
        
        # Ensure all messages are sent
        remaining = kafka_service.flush(10)
        if remaining > 0:
            logger.warning(f"{remaining} messages were not delivered")
        else:
            logger.info(f"All chunks successfully sent to Kafka")
        
        # Return success with chunks
        return result
        
    except Exception as e:
        logger.error(f"Error in process_url_and_send_to_kafka: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}