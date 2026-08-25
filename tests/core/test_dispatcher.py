"""Tests for src/core/notifications/dispatcher.py.

Focus: per-channel HTML rendering. The dispatcher must inspect the resolved
Apprise plugin's notify_format and:
- HTML targets → render the body via markdown_to_email_html and dispatch with
  body_format=HTML;
- non-HTML targets → dispatch unchanged with body_format=MARKDOWN.

We patch apprise.Apprise.async_notify to capture the kwargs so the assertions
focus on contract, not Apprise internals.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import apprise
import pytest

from src.core.crypto import encrypt_apprise_url
from src.core.notifications import constants
from src.core.notifications import dispatcher as dispatcher_module
from src.core.notifications.constants import APP_URL_ENV_VAR
from src.core.notifications.dispatcher import _build_asset, dispatch_to_channel


@pytest.fixture
def captured_notify():
    """Patch Apprise.async_notify to capture kwargs and return success."""
    mock = AsyncMock(return_value=True)
    with patch.object(apprise.Apprise, "async_notify", mock):
        yield mock


async def test_html_native_channel_renders_html_body(captured_notify):
    encrypted = encrypt_apprise_url("mailto://user:pass@example.com")
    body = "```diff\n+ added\n- removed\n```\n"

    result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body=body)

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

    result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body=body)

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

    result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body="b")

    assert result.success is False
    captured_notify.assert_not_awaited()


class TestBrandingAsset:
    """The Apprise asset carries branding into delivered notifications.

    `app_url` was hardcoded to https://notifier.exe.xyz, a hostname with no DNS
    record — the VM is named `watcher`, and notifier is a co-located service,
    not a host. Six Apprise plugins embed that value as a clickable link
    (discord, msteams, sparkpost, workflows, notificationapi, fluxer), so any
    channel on one of them would have shipped a dead link to real recipients.
    Slack and Mailgun, the two channels in use, ignore it — which is why this
    went unnoticed.
    """

    def test_ships_no_url_by_default(self):
        """Same reasoning as image_url_mask/logo beside it: emit nothing
        rather than a link we do not control. Apprise treats a falsy app_url
        as absent (apprise/url.py app_url property), so plugins omit it."""
        assert _build_asset().app_url == ""

    def test_url_is_configurable(self, monkeypatch):
        monkeypatch.setenv(APP_URL_ENV_VAR, "https://notify.example.test")
        assert _build_asset().app_url == "https://notify.example.test"

    def test_branding_identity_is_unconditional(self):
        """Suppressing the link must not blank the name and description too."""
        asset = _build_asset()
        assert asset.app_id == "Notifier"
        assert "Notifier" in asset.app_desc

    def test_no_vm_hostname_is_hardcoded(self):
        """Regression guard against reintroducing the dead default.

        Reads code lines only. Both modules explain the dead hostname in
        comments, and a raw-text match would make those comments fail the test
        they document — the same reason `tests/deploy/test_dev_systemd_unit.py`
        checks systemd directives rather than file text.
        """
        for module in (dispatcher_module, constants):
            code = "\n".join(
                line
                for line in Path(module.__file__).read_text().splitlines()
                if not line.lstrip().startswith("#")
            )
            assert "exe.xyz" not in code
