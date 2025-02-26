# Confluent Documentation Tools

A modular application that scrapes URLs, chunks the content, and streams the chunks to Kafka for integration with MongoDB and RAG systems.

## Features

- **Documentation Assistant**: Ask questions about Confluent documentation
- **URL Chunker**: Process URLs and send chunks to Kafka
- **Processed URLs**: View history of all processed URLs

## Project Structure

```
├── app.py                 # Main application entry point
├── ui.py                  # Streamlit UI components
├── config_utils.py        # Configuration management
├── db_utils.py            # MongoDB and vector search utilities
├── kafka_utils.py         # Kafka producer and chunker utilities
├── openai_utils.py        # OpenAI API integration
├── model_utils.py         # Abstract model provider interface
├── config.json            # Application configuration
└── requirements.txt       # Project dependencies
```

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Create a `config.json` file with your API keys and configurations:
   ```json
   {
     "kafka_bootstrap_servers": "your-kafka-server:9092",
     "kafka_api_key": "YOUR_KAFKA_API_KEY",
     "kafka_api_secret": "YOUR_KAFKA_API_SECRET",
     "kafka_topic": "website_chunks",
     "schema_registry_url": "https://your-schema-registry-url",
     "schema_registry_api_key": "YOUR_SR_API_KEY",
     "schema_registry_api_secret": "YOUR_SR_API_SECRET",
     "openai_api_key": "YOUR_OPENAI_API_KEY",
     "mongodb_uri": "mongodb+srv://user:pass@cluster.mongodb.net/",
     "mongodb_database": "documentation",
     "mongodb_collection": "chunks",
     "chunker_api_url": "https://your-chunker-api-url.com/chunk",
     "llm_provider": "openai",
     "function_model": "gpt-4o",
     "response_model": "gpt-4o-mini"
   }
   ```

3. Run the application:
   ```
   streamlit run app.py
   ```

## Adding New LLM Providers

To add support for a new LLM provider:

1. Create a new file (e.g., `anthropic_utils.py`) that implements the `LLMProvider` interface
2. Add your provider to the factory function in `model_utils.py`
3. Update your `config.json` to use the new provider with `"llm_provider": "anthropic"`

## URL Processing Flow

1. User enters a URL in the UI
2. URL is sent to the chunker API
3. Chunks are processed and sent to Kafka
4. Flink processes and generates embeddings
5. Data is stored in MongoDB
6. The URL history is displayed in the UI

## Maintaining URL History

All processed URLs are stored in MongoDB in the `processed_urls` collection. The UI displays these URLs in the "Processed URLs" tab.