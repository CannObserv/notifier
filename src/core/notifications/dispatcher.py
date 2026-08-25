"""Apprise-based notification dispatcher."""

import asyncio
import contextvars
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

import apprise
from apprise import AppriseAsset, NotifyFormat, NotifyType

from src.core.crypto import decrypt_apprise_url
from src.core.logging import get_logger
from src.core.notifications.constants import APP_URL_ENV_VAR
from src.core.notifications.html_render import markdown_to_email_html

logger = get_logger(__name__)


def _build_asset() -> AppriseAsset:
    """Brand identity for all outbound notifications.

    Three fields are deliberately suppressed rather than defaulted:
    ``image_url_mask`` and ``image_url_logo`` so plugins don't pull Apprise CDN
    icons, and ``app_url`` — unset unless ``NOTIFIER_APP_URL`` names a real
    address — so no plugin embeds a link that does not resolve. Apprise's own
    default for ``app_url`` is the Apprise GitHub repo, which would be someone
    else's branding on our notifications; its ``app_url`` property maps any
    falsy value to ``""`` and plugins then omit the link entirely.

    A function rather than a module constant so the environment is read where
    it is used, and so tests can build an asset without reimporting the module
    (which would mint fresh copies of the enums in ``constants``).
    """
    return AppriseAsset(
        app_id="Notifier",
        app_desc="Notifier — multi-tenant notifications service",
        app_url=os.environ.get(APP_URL_ENV_VAR, ""),
        image_url_mask="",
        image_url_logo="",
    )


_ASSET = _build_asset()

# Per-task capture buffer for Apprise WARNING log messages.
# Each asyncio task gets its own context copy, so concurrent dispatch calls
# are fully isolated — no cross-contamination between tenants.
#
# The isolation is why this is a contextvar, and the thread hop below is why
# reaching it takes care: Apprise runs a sync plugin's send() in a worker
# thread, and only `asyncio.to_thread` copies the calling context across (see
# dispatch_to_channel).
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


def _describe_target(server: object) -> str:
    """Name a channel's target without quoting its URL.

    The URL is the credential — `reason` is persisted and handed back over the
    API, so it may carry the plugin and the address, never the secret.
    """
    name = type(server).__name__
    host = getattr(server, "host", None)
    port = getattr(server, "port", None)
    if host and port:
        return f"{name} ({host}:{port})"
    if host:
        return f"{name} ({host})"
    return name


def _scrub(text: str, url: str) -> str:
    """Strip a channel's credentials out of text bound for the API.

    Apprise messages and third-party exceptions both quote the URL they were
    given — `requests` puts the full URL in several of its exception strings.
    Anything derived from them passes through here first.
    """
    parts = urlsplit(url)
    scrubbed = text.replace(url, "<channel url>")
    for secret in (parts.password, parts.username):
        if secret:
            scrubbed = scrubbed.replace(secret, "***")
    return scrubbed


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

    Decrypts the stored URL, hands it to Apprise, and runs the notification
    on a worker thread. Returns a DispatchResult with success flag and
    human-readable reason. Apprise WARNING log messages emitted during the
    call are captured and included in the reason on failure, surfacing
    actionable error detail (e.g. Slack's not_in_channel, HTTP 401 bodies).

    Uses the synchronous ``notify`` under ``asyncio.to_thread`` rather than
    ``async_notify``. Apprise's async path ends in
    ``loop.run_in_executor(None, send)``, and ``run_in_executor`` does not
    copy the caller's context into the worker thread — so every WARNING a
    plugin logged landed where the capture buffer was invisible, and the
    reason read "no detail captured" for every HTTP plugin in production
    (#25). ``asyncio.to_thread`` copies the context, which is the whole
    difference. Both spellings hand the work to the same executor, so nothing
    blocks the event loop either way.

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
        result = await asyncio.to_thread(
            ap.notify,
            body=send_body,
            title=title,
            notify_type=notify_type,
            body_format=send_format,
        )
    except Exception as exc:
        # One channel's plugin misbehaving is that channel's failure, not the
        # whole dispatch request's. Apprise catches most of these itself; this
        # covers what it re-raises and anything thrown before it takes over.
        logger.exception("apprise raised while dispatching")
        detail = _scrub(f"{type(exc).__name__}: {exc}", url)
        return DispatchResult(success=False, reason=f"Delivery failed: {detail}")
    finally:
        _capture_ctx.reset(token)

    if result is True:
        return DispatchResult(success=True, reason="Notification sent successfully")
    detail = (
        _scrub("; ".join(messages), url)
        if messages
        else (f"{_describe_target(ap.servers[0])} reported no error detail")
    )
    return DispatchResult(success=False, reason=f"Delivery failed: {detail}")
