# openai_utils.py
import json
import logging
from typing import Dict, Any, List, Optional
from functools import wraps
from tenacity import retry, stop_after_attempt, wait_exponential

# OpenAI import
from openai import OpenAI

# Import from modular utilities
from config_utils import load_config
from db_utils import get_mongodb_instance

# Constants
FUNCTION_CALLING_MODEL = "gpt-4o"
RESPONSE_GENERATION_MODEL = "gpt-4o-mini"

# Configure logging
logger = logging.getLogger("openai")

class OpenAIClient:
    """Handles interactions with OpenAI API."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize OpenAI client with API key."""
        try:
            self.client = OpenAI(api_key=config['openai_api_key'])
            self.function_model = config.get('function_model', FUNCTION_CALLING_MODEL)
            self.response_model = config.get('response_model', RESPONSE_GENERATION_MODEL)
            self.timeout = config.get('openai_timeout', 30)
            logger.info(f"OpenAI client initialized with models: {self.function_model} and {self.response_model}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a text using OpenAI's embedding model."""
        try:
            # Truncate text if too long
            if len(text) > 4000:
                text = text[:4000]
                
            response = self.client.embeddings.create(
                model="text-embedding-ada-002",
                input=text,
                encoding_format="float"
            )
            
            embedding = response.data[0].embedding
            return embedding
        except Exception as e:
            logger.error(f"Failed to get embedding: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
    def should_search_knowledge_base(self, query: str) -> Dict[str, Any]:
        """Determine if the query requires searching the knowledge base."""
        try:
            # Define the function for tool calling
            tools = [{
                "type": "function",
                "function": {
                    "name": "search_knowledge_base",
                    "description": "Search the Confluent documentation to find information that helps answer the query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "should_search": {
                                "type": "boolean",
                                "description": "Whether to search the knowledge base or not. Set to true if the query is about Confluent products, services, or documentation."
                            },
                            "search_query": {
                                "type": "string",
                                "description": "The refined search query to use when querying the knowledge base."
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of top results to return, between 1 and 10."
                            }
                        },
                        "required": ["should_search", "search_query", "num_results"],
                        "additionalProperties": False
                    }
                }
            }]
            
            messages = [
                {"role": "system", "content": "You are an assistant that helps determine if a user query requires searching Confluent documentation."},
                {"role": "user", "content": query}
            ]
            
            response = self.client.chat.completions.create(
                model=self.function_model,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            # Extract the function call if available
            if response.choices[0].message.tool_calls:
                tool_call = response.choices[0].message.tool_calls[0]
                function_args = json.loads(tool_call.function.arguments)
                logger.info(f"Function call decision: {function_args}")
                return function_args
            else:
                # Default behavior if no tool call is made
                logger.info("No tool call made, defaulting to no search")
                return {
                    "should_search": False,
                    "search_query": query,
                    "num_results": 3
                }
                
        except Exception as e:
            logger.error(f"Failed to determine if knowledge base search is needed: {str(e)}")
            # Default to search on failure
            return {
                "should_search": True,
                "search_query": query,
                "num_results": 3
            }

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
    def generate_response(self, query: str, context: Optional[str] = None) -> str:
        """Generate a response using OpenAI's chat model."""
        try:
            # Prepare system message based on whether context is provided
            if context:
                # Truncate context if too long
                # if len(context) > 3000:
                #     context = context[:3000]
                    
                system_content = f"""You are a helpful assistant for Confluent that answers questions based on the provided context. 
                    Your task:
                    1. Carefully analyze the provided CONTEXT sections below
                    2. Extract relevant information that directly addresses the user's question
                    3. Provide a comprehensive, detailed answer based ONLY on the information in the context
                    4. If the context doesn't contain enough information to fully answer the question, acknowledge this limitation
                    5. Format your response with clear headings, bullet points, and code examples (if relevant)
                    6. Never make up information that is not in the context

                    CONTEXT:
                    {context}
                    Remember: Base your answer ONLY on the information provided in the context. If information is missing, say "Based on the available documentation, I don't have complete information about [specific topic]" rather than making up details."""
            else:
                system_content = """You are a helpful assistant for Confluent. 
                If you don't know the answer, simply say so. Don't make up information."""
            
            logger.info(f"\n\n---- prompt ------\n\n {system_content}\n\n question = {query}")
            messages = [
                # {"role": "system", "content": system_content},
                {"role": "user", "content": system_content+"\n"+query}
            ]
            
            response = self.client.chat.completions.create(
                model=self.response_model,
                messages=messages,
                temperature=0.1,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Failed to generate response: {str(e)}")
            return "I'm sorry, I encountered an error while generating a response."

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
    def rewrite_query(self, query: str) -> str:
        """Rewrite the query to make it more suitable for vector search."""
        try:
            system_content = """You are a specialized query reformulation assistant for Confluent Cloud technical documentation. Your task is to rewrite user queries to maximize vector search relevance.
            When rewriting queries:

            1. ESSENTIAL: Preserve all original product names and technical terms EXACTLY as written (e.g., "Standard cluster" must remain "Standard cluster")
            2. Structure queries in multiple complementary ways within a single query:
            - Direct specifications: "What are the exact technical specifications of [product]?"
            - Comparative: "How does [product] compare to other tiers like Basic/Dedicated/Enterprise in terms of limits and capabilities?"
            - Feature-focused: "What specific features and limitations are included in [product]?"
            3. Always include relevant technical parameters like:
            - Throughput (ingress/egress)
            - Storage capacity
            - Partition limits
            - Connection limits
            - Available regions/availability
            - Pricing model (if relevant)
            4. Use Confluent Cloud's exact terminology for cluster types (Standard, Dedicated, Enterprise, Basic)
            5. Format using short, direct questions that would appear in documentation
            6. Keep under 120 words total

            Example:
            Original query: 'what does Standard cluster provide in confluent cloud?'
            Rewritten query: 'What are the exact technical specifications of Standard cluster in Confluent Cloud? What ingress/egress throughput, storage limits, partition counts, and connection limits apply to Standard cluster? How does Standard cluster compare to Dedicated and Enterprise clusters in terms of capabilities and limitations? What specific features are included with Standard cluster?'

            Respond ONLY with the rewritten query, without any additional text."""
            
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": f"Rewrite this query for vector search: {query}"}
            ]
            
            response = self.client.chat.completions.create(
                model=self.response_model,  # Using the smaller model for speed
                messages=messages,
                temperature=0.1,  # Low temperature for deterministic results
                max_tokens=200
            )
            
            rewritten_query = response.choices[0].message.content.strip()
            logger.info(f"Original query: '{query}'\n========\nRewritten query: '{rewritten_query}'")
            return rewritten_query
            
        except Exception as e:
            logger.error(f"Failed to rewrite query: {str(e)}")
            # On failure, return the original query
            return query

# Singleton pattern for OpenAI client
_openai_client = None

def get_openai_client() -> OpenAIClient:
    """Get or create OpenAI client using singleton pattern."""
    global _openai_client
    if _openai_client is None:
        config = load_config()
        _openai_client = OpenAIClient(config)
    return _openai_client

class ConfluentRAG:
    """Retrieval-Augmented Generation system for Confluent documentation."""
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize the RAG system with configuration."""
        try:
            self.config = load_config(config_path)
            self.mongodb = get_mongodb_instance()
            self.openai_client = get_openai_client()
            logger.info("ConfluentRAG initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ConfluentRAG: {str(e)}")
            raise

    def answer_question(self, query: str) -> str:
        """Generate an answer for the user's question using an agentic approach."""
        try:
            # Check for empty query
            if not query or not query.strip():
                return "Please ask a question about Confluent."
            
            # Use function calling to determine if we should search the knowledge base
            search_decision = self.openai_client.should_search_knowledge_base(query)
            
            # If the model decides we should search
            if search_decision["should_search"]:
                # First, rewrite the query to optimize for vector search
                rewritten_query = self.openai_client.rewrite_query(query)
                
                # Get embedding for the rewritten query (not the original search_query from function calling)
                query_embedding = self.openai_client.get_embedding(rewritten_query)
                
                # Search for relevant documents using the rewritten query
                results = self.mongodb.vector_search(
                    query_embedding, 
                    limit= 3, # search_decision["num_results"],
                    query_text=rewritten_query
                )
                
                if results:
                    # Extract and format the context from the search results
                    context = "\n\n".join([doc["chunk_content"] for doc in results])
                    logger.info(f"context = {context}\n\n")
                    
                    # Generate response using the context with the ORIGINAL query
                    # This is important - we use the rewritten query for search but the original query for answering
                    return self.openai_client.generate_response(query, context)
                else:
                    # No results found, generate response without context
                    return self.openai_client.generate_response(
                        query,
                        "I searched the Confluent documentation but couldn't find specific information about this."
                    )
            else:
                # Model decided no need to search, generate response directly
                logger.info("Skipping knowledge base search as per model decision")
                return self.openai_client.generate_response(query)
                
        except Exception as e:
            logger.error(f"Error answering question: {str(e)}")
            return "I'm sorry, I encountered an error while processing your question."

