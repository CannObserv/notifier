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
from notifier_client.types import (
    AssembleResponse,
    ChannelOut,
    ChannelTestResponse,
    DispatchAttemptOut,
    DispatchAttemptOutStatus,
    DispatchOut,
    DispatchOutStatus,
    PluginDetail,
    PluginListItem,
    PreviewResponse,
    TemplateOut,
    TemplatePreviewResponse,
)

__version__ = "0.2.1"

__all__ = [
    "__version__",
    "AUTO",
    "AssembleResponse",
    "AuthError",
    "ChannelOut",
    "ChannelTestResponse",
    "DispatchAttemptOut",
    "DispatchAttemptOutStatus",
    "DispatchOut",
    "DispatchOutStatus",
    "NotifierClient",
    "NotifierError",
    "PluginDetail",
    "PluginListItem",
    "PreviewResponse",
    "RateLimited",
    "RedactingFilter",
    "RetryConfig",
    "ServerError",
    "TemplateOut",
    "TemplatePreviewResponse",
    "ValidationError",
]
