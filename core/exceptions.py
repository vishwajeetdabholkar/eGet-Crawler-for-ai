from typing import List, Optional, Any, Dict
from http import HTTPStatus

class ScraperException(Exception):
    """Base exception class for scraper errors"""
    def __init__(
        self,
        message: str,
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
        error_code: str = "SCRAPER_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary format"""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "status": self.status_code,
                "details": self.details
            }
        }

class URLFetchError(ScraperException):
    """Raised when unable to fetch content from URL"""
    def __init__(self, url: str, reason: str, status_code: Optional[int] = None):
        super().__init__(
            message=f"Failed to fetch URL: {url}",
            status_code=status_code or HTTPStatus.BAD_REQUEST,
            error_code="URL_FETCH_ERROR",
            details={
                "url": url,
                "reason": reason
            }
        )

class ContentExtractionError(ScraperException):
    """Raised when content extraction fails"""
    def __init__(self, reason: str):
        super().__init__(
            message="Failed to extract content",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code="CONTENT_EXTRACTION_ERROR",
            details={"reason": reason}
        )

class BrowserError(ScraperException):
    """Raised when browser-related operations fail"""
    def __init__(self, action: str, reason: str):
        super().__init__(
            message=f"Browser operation failed: {action}",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code="BROWSER_ERROR",
            details={
                "action": action,
                "reason": reason
            }
        )

class RateLimitExceeded(ScraperException):
    """Raised when rate limit is exceeded"""
    def __init__(self, limit: int, period: int):
        super().__init__(
            message=f"Rate limit of {limit} requests per {period} seconds exceeded",
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            details={
                "limit": limit,
                "period": period
            }
        )

class ValidationError(ScraperException):
    """Raised when request validation fails"""
    def __init__(self, errors: List[Dict[str, Any]]):
        super().__init__(
            message="Request validation failed",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            details={"errors": errors}
        )

class ConfigurationError(ScraperException):
    """Raised when there's a configuration error"""
    def __init__(self, parameter: str, reason: str):
        super().__init__(
            message=f"Configuration error: {parameter}",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code="CONFIGURATION_ERROR",
            details={
                "parameter": parameter,
                "reason": reason
            }
        )

class ResourceCleanupError(ScraperException):
    """Raised when resource cleanup fails"""
    def __init__(self, resource_type: str, reason: str):
        super().__init__(
            message=f"Failed to cleanup {resource_type}",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code="RESOURCE_CLEANUP_ERROR",
            details={
                "resource_type": resource_type,
                "reason": reason
            }
        )

class TimeoutError(ScraperException):
    """Raised when an operation times out"""
    def __init__(self, operation: str, timeout: int):
        super().__init__(
            message=f"Operation timed out: {operation}",
            status_code=HTTPStatus.REQUEST_TIMEOUT,
            error_code="TIMEOUT_ERROR",
            details={
                "operation": operation,
                "timeout_seconds": timeout
            }
        )