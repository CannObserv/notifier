"""Apprise-based notification dispatcher."""

import contextvars
import logging
from dataclasses import dataclass

import apprise
from apprise import AppriseAsset, NotifyFormat, NotifyType

from src.core.crypto import decrypt_apprise_url
from src.core.logging import get_logger
from src.core.notifications.constants import APP_URL
from src.core.notifications.html_render import markdown_to_email_html

logger = get_logger(__name__)

# Brand identity for all outbound notifications.
# image_url_mask/logo suppressed (empty) so plugins don't pull Apprise CDN icons.
_ASSET = AppriseAsset(
    app_id="Notifier",
    app_desc="Notifier — multi-tenant notifications service",
    app_url=APP_URL,
    image_url_mask="",
    image_url_logo="",
)

# Per-task capture buffer for Apprise WARNING log messages.
# Each asyncio task gets its own context copy, so concurrent dispatch calls
# are fully isolated — no cross-contamination between tenants.
_capture_ctx: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "_apprise_capture", default=None
)


class _AppriseCapturingFilter(logging.Filter):
    """Appends WARNING+ apprise log messages to the current task's capture buffer."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            buf = _capture_ctx.get()
            if buf is not None:
                buf.append(record.getMessage())
        return True  # never suppress


# Attached once at module load; zero cost when no capture buffer is set.
logging.getLogger("apprise").addFilter(_AppriseCapturingFilter())


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Outcome of a single Apprise dispatch attempt."""

    success: bool
    reason: str


async def dispatch_to_channel(
    *,
    apprise_url_encrypted: str,
    title: str,
    body: str,
    notify_type: NotifyType = NotifyType.INFO,
) -> DispatchResult:
    """Dispatch a rendered notification to a single Apprise target.

    Decrypts the stored URL, hands it to Apprise, and awaits async_notify.
    Returns a DispatchResult with success flag and human-readable reason.
    Apprise WARNING log messages emitted during the call are captured and
    included in the reason on failure, surfacing actionable error detail
    (e.g. Slack's not_in_channel, HTTP 401 bodies).

    Service-level concern: callers must already have rendered title and body.
    The dispatcher is template-agnostic.
    """
    url = decrypt_apprise_url(apprise_url_encrypted)
    ap = apprise.Apprise(asset=_ASSET)
    if not ap.add(url):
        logger.warning("invalid apprise url in channel config")
        return DispatchResult(
            success=False, reason="Invalid Apprise URL: check your channel configuration"
        )

    # Per-channel format negotiation: HTML-native plugins (mailto, sendgrid, etc.)
    # get a Markdown→HTML rewrite with colored diff fences; everything else
    # receives the source Markdown unchanged.
    plugin_format = getattr(ap.servers[0], "notify_format", NotifyFormat.MARKDOWN)
    if plugin_format == NotifyFormat.HTML:
        send_body = markdown_to_email_html(body)
        send_format = NotifyFormat.HTML
    else:
        send_body = body
        send_format = NotifyFormat.MARKDOWN
    logger.debug("dispatching with body_format=%s", send_format.value)

    messages: list[str] = []
    token = _capture_ctx.set(messages)
    try:
        result = await ap.async_notify(
            body=send_body,
            title=title,
            notify_type=notify_type,
            body_format=send_format,
        )
    finally:
        _capture_ctx.reset(token)

    if result is True:
        return DispatchResult(success=True, reason="Notification sent successfully")
    detail = "; ".join(messages) or "no detail captured"
    return DispatchResult(success=False, reason=f"Delivery failed: {detail}")
