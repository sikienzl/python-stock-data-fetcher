class APIError(Exception):
    """Base exception for API-related errors."""
    pass

class RateLimitError(APIError):
    """Raised when the API rate limit is exceeded."""
    pass

class InvalidSymbolError(APIError):
    """Raised when the stock symbol is invalid."""
    pass