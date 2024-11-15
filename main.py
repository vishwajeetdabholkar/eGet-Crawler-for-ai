from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import uvicorn
import time
from loguru import logger
from contextlib import asynccontextmanager
from prometheus_client import make_asgi_app

from core.config import settings
from core.exceptions import ScraperException, ValidationError
from models.request import ScrapeRequest
from services.scraper.scraper import WebScraper
from services.crawler.crawler_service import CrawlerService 
from api.v1.endpoints import crawler, scraper  

# Prometheus metrics endpoint
metrics_app = make_asgi_app()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for the application"""
    try:
        # Startup
        logger.info("Initializing application...")
        
        # Initialize resources
        logger.info("Initializing scraper...")
        app.state.scraper = WebScraper(max_concurrent=settings.CONCURRENT_SCRAPES)
        logger.info("Initializing crawler...")
        app.state.crawler = CrawlerService(max_concurrent=settings.CONCURRENT_SCRAPES) 
        
        yield
        
        # Shutdown
        logger.info("Shutting down application...")
        await app.state.scraper.cleanup()
    except Exception as e:
        logger.exception(f"Application lifecycle error: {str(e)}")
        raise

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-grade web scraper API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    crawler.router,
    prefix="/api/v1",
    tags=["crawler"]
)

app.include_router(
    scraper.router,
    prefix="/api/v1",
    tags=["scraper"] 
)

app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=settings.ALLOWED_HOSTS
)

# Custom middleware for request timing
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ValidationError(errors=exc.errors()).to_dict()
    )

@app.exception_handler(ScraperException)
async def scraper_exception_handler(request: Request, exc: ScraperException):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "status": 500
            }
        }
    )

# Mount Prometheus metrics endpoint
app.mount("/metrics", metrics_app)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time()
    }

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": settings.PROJECT_NAME,
        "version": "1.0.0",
        "description": "Production-grade web scraper API",
        "docs_url": "/docs",
        "health_check": "/health"
    }

@app.post("/scrape", response_model_exclude_none=True)
async def scrape_url(request: ScrapeRequest, req: Request):
    """
    Scrape a URL and return processed content
    """
    logger.info(f"Processing scrape request for URL: {request.url}")
    
    options = {
        "only_main": request.onlyMainContent,
        "timeout": request.timeout or settings.TIMEOUT,
        "user_agent": settings.DEFAULT_USER_AGENT,
        "headers": request.headers,
        "screenshot": True,
        "screenshot_quality": settings.SCREENSHOT_QUALITY,
        "wait_for_selector": request.waitFor
    }
    
    if request.actions:
        options["actions"] = request.actions
    
    result = await req.app.state.scraper.scrape(str(request.url), options)
    return result

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower()
    )