"""Tests for src/core/notifications/dispatcher.py.

Focus: per-channel HTML rendering. The dispatcher must inspect the resolved
Apprise plugin's notify_format and:
- HTML targets → render the body via markdown_to_email_html and dispatch with
  body_format=HTML;
- non-HTML targets → dispatch unchanged with body_format=MARKDOWN.

We patch apprise.Apprise.async_notify to capture the kwargs so the assertions
focus on contract, not Apprise internals.
"""

from unittest.mock import AsyncMock, patch

import apprise
import pytest

from src.core.crypto import encrypt_apprise_url
from src.core.notifications.dispatcher import dispatch_to_channel


@pytest.fixture
def captured_notify():
    """Patch Apprise.async_notify to capture kwargs and return success."""
    mock = AsyncMock(return_value=True)
    with patch.object(apprise.Apprise, "async_notify", mock):
        yield mock


async def test_html_native_channel_renders_html_body(captured_notify):
    encrypted = encrypt_apprise_url("mailto://user:pass@example.com")
    body = "```diff\n+ added\n- removed\n```\n"

    result = await dispatch_to_channel(
        apprise_url_encrypted=encrypted, title="t", body=body
    )

    assert result.success is True
    captured_notify.assert_awaited_once()
    kwargs = captured_notify.await_args.kwargs
    assert kwargs["body_format"] == apprise.NotifyFormat.HTML
    sent_body = kwargs["body"]
    assert "background:#e6ffec" in sent_body
    assert "background:#ffebe9" in sent_body
    assert "+ added" in sent_body
    assert "- removed" in sent_body


async def test_non_html_channel_dispatches_markdown_unchanged(captured_notify):
    encrypted = encrypt_apprise_url("json://example.com")
    body = "```diff\n+ added\n```\n"

    result = await dispatch_to_channel(
        apprise_url_encrypted=encrypted, title="t", body=body
    )

    assert result.success is True
    captured_notify.assert_awaited_once()
    kwargs = captured_notify.await_args.kwargs
    assert kwargs["body_format"] == apprise.NotifyFormat.MARKDOWN
    # Body is the raw Markdown source, not the HTML rewrite.
    assert kwargs["body"] == body
    assert "<pre" not in kwargs["body"]


async def test_html_native_channel_renders_plain_markdown_too(captured_notify):
    """Non-diff Markdown still goes through the HTML pipeline for HTML targets."""
    encrypted = encrypt_apprise_url("mailto://user:pass@example.com")

    result = await dispatch_to_channel(
        apprise_url_encrypted=encrypted, title="t", body="**bold** text\n"
    )

    assert result.success is True
    sent_body = captured_notify.await_args.kwargs["body"]
    assert captured_notify.await_args.kwargs["body_format"] == apprise.NotifyFormat.HTML
    assert "<strong>" in sent_body


async def test_invalid_apprise_url_returns_failure_without_notify(captured_notify):
    """add() failing must short-circuit before any notify call."""
    encrypted = encrypt_apprise_url("not-a-real-scheme://oops")

    result = await dispatch_to_channel(
        apprise_url_encrypted=encrypted, title="t", body="b"
    )

    assert result.success is False
    captured_notify.assert_not_awaited()
