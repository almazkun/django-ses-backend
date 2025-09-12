from .sync import SESEmailBackend

try:
    from .a_sync import AsyncSESEmailBackend, AsyncSESClient

    __all__ = ["SESEmailBackend", "AsyncSESEmailBackend", "AsyncSESClient"]
except ImportError:
    __all__ = ["SESEmailBackend"]
