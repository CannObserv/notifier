"""notifier-client — async Python SDK for the notifier service.

Pinned 1:1 with notifier server version. See README for usage.
"""

from notifier_client.client import NotifierClient
from notifier_client.errors import (
    AuthError,
    NotifierError,
    RateLimited,
    ServerError,
    ValidationError,
)
from notifier_client.idempotency import AUTO
from notifier_client.logging import RedactingFilter
from notifier_client.retry import RetryConfig

__version__ = "0.1.0"

__all__ = [
    "AUTO",
    "AuthError",
    "NotifierClient",
    "NotifierError",
    "RateLimited",
    "RedactingFilter",
    "RetryConfig",
    "ServerError",
    "ValidationError",
    "__version__",
]
