# app.py
import sys
import logging
from config_utils import load_config

# Configure logging for the main application
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("app")

def main():
    """Main entry point for the application."""
    try:
        # Load configuration to ensure it exists
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Import here to avoid circular imports
        from ui import create_streamlit_app
        
        # Launch the Streamlit app
        logger.info("Starting unified Streamlit application")
        create_streamlit_app()
        
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()