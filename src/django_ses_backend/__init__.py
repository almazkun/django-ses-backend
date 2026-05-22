from .backends.sync import SESEmailBackend
from .exceptions import SESClientError, SESRateLimitError, SESRetryableClientError

try:
    from .backends.a_sync import AsyncSESEmailBackend, AsyncSESClient

    __all__ = [
        "SESEmailBackend",
        "AsyncSESEmailBackend",
        "AsyncSESClient",
        "SESClientError",
        "SESRateLimitError",
        "SESRetryableClientError",
    ]
except ImportError:
    __all__ = [
        "SESEmailBackend",
        "SESClientError",
        "SESRateLimitError",
        "SESRetryableClientError",
    ]
