"""notifier-client — async Python SDK for the notifier service.

Versioned in lockstep with the notifier server: this package's version is the
version of the server it was generated from. Enforced by the repo's
``tests/ci/test_version_lockstep.py``, not by convention. See README for usage.
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

__version__ = "0.3.1"

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
