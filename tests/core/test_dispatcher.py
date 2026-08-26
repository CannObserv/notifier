"""Tests for src/core/notifications/dispatcher.py.

Focus: per-channel HTML rendering. The dispatcher must inspect the resolved
Apprise plugin's notify_format and:
- HTML targets → render the body via markdown_to_email_html and dispatch with
  body_format=HTML;
- non-HTML targets → dispatch unchanged with body_format=MARKDOWN.

We patch apprise.Apprise.async_notify to capture the kwargs so the assertions
focus on contract, not Apprise internals.
"""

import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import apprise
import pytest

from src.core.crypto import encrypt_apprise_url
from src.core.notifications import constants
from src.core.notifications import dispatcher as dispatcher_module
from src.core.notifications.constants import APP_URL_ENV_VAR
from src.core.notifications.dispatcher import _build_asset, dispatch_to_channel


@pytest.fixture
def captured_notify():
    """Patch Apprise.notify to capture kwargs and return success.

    `notify`, not `async_notify`: the dispatcher drives the synchronous call
    through `asyncio.to_thread` so the capture buffer survives the hop into
    the worker thread (#25).
    """
    mock = MagicMock(return_value=True)
    with patch.object(apprise.Apprise, "notify", mock):
        yield mock


async def test_html_native_channel_renders_html_body(captured_notify):
    encrypted = encrypt_apprise_url("mailto://user:pass@example.com")
    body = "```diff\n+ added\n- removed\n```\n"

    result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body=body)

    assert result.success is True
    captured_notify.assert_called_once()
    kwargs = captured_notify.call_args.kwargs
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
    captured_notify.assert_called_once()
    kwargs = captured_notify.call_args.kwargs
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
    sent_body = captured_notify.call_args.kwargs["body"]
    assert captured_notify.call_args.kwargs["body_format"] == apprise.NotifyFormat.HTML
    assert "<strong>" in sent_body


async def test_invalid_apprise_url_returns_failure_without_notify(captured_notify):
    """add() failing must short-circuit before any notify call."""
    encrypted = encrypt_apprise_url("not-a-real-scheme://oops")

    result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body="b")

    assert result.success is False
    captured_notify.assert_not_called()


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


def _closed_port() -> int:
    """A port nothing is listening on, so connecting is refused immediately."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestFailureDetail:
    """Why a dispatch failed has to survive the trip back to the consumer.

    `reason` is the only diagnostic the API hands a consumer, and in production
    it read "Delivery failed: no detail captured" for every HTTP plugin — see
    #25. The capture buffer is a contextvar, and Apprise runs a sync plugin's
    send() through `loop.run_in_executor`, which does *not* copy the caller's
    context. The WARNING Apprise logs is correct, well-worded, and lands in a
    thread where the buffer is invisible.

    Every existing test patches `Apprise.async_notify`, so none of them ever
    crossed that thread boundary — which is exactly why a feature that never
    worked once in production had a green suite behind it.
    """

    async def test_apprise_detail_survives_the_thread_hop(self):
        """No patching: this is the path production takes."""
        encrypted = encrypt_apprise_url(f"json://127.0.0.1:{_closed_port()}/notify")

        result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body="b")

        assert result.success is False
        assert "no detail captured" not in result.reason
        assert "Connection error" in result.reason

    async def test_reason_names_the_target_when_apprise_reports_nothing(self):
        """A silent False still has to say what could not be reached."""
        port = _closed_port()
        encrypted = encrypt_apprise_url(f"json://127.0.0.1:{port}/notify")

        with patch.object(apprise.Apprise, "notify", MagicMock(return_value=False)):
            result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body="b")

        assert result.success is False
        assert "NotifyJSON" in result.reason
        assert f"127.0.0.1:{port}" in result.reason

    async def test_an_exception_becomes_a_reason_not_a_500(self):
        """A plugin blowing up is one channel's failure, not the request's."""
        encrypted = encrypt_apprise_url("json://127.0.0.1:1/notify")

        with patch.object(apprise.Apprise, "notify", MagicMock(side_effect=RuntimeError("boom"))):
            result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body="b")

        assert result.success is False
        assert "RuntimeError" in result.reason
        assert "boom" in result.reason

    async def test_reason_never_carries_the_credential(self):
        """`reason` is persisted and returned over the API; the URL is a secret."""
        encrypted = encrypt_apprise_url(f"json://user:hunter2@127.0.0.1:{_closed_port()}/notify")

        result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body="b")

        assert result.success is False
        assert "hunter2" not in result.reason

    async def test_exception_text_is_scrubbed_too(self):
        """`requests` quotes the full URL in several of its exception strings."""
        encrypted = encrypt_apprise_url("json://user:hunter2@127.0.0.1:1/notify")
        boom = RuntimeError("failed posting to json://user:hunter2@127.0.0.1:1/notify")

        with patch.object(apprise.Apprise, "notify", MagicMock(side_effect=boom)):
            result = await dispatch_to_channel(apprise_url_encrypted=encrypted, title="t", body="b")

        assert result.success is False
        assert "hunter2" not in result.reason
        assert "RuntimeError" in result.reason


class TestWireFormat:
    """What actually leaves the process, asserted against a real target.

    The format-negotiation tests above read `Apprise.notify`'s kwargs through
    a mock. That is one boundary short of the wire, and being one boundary
    short of the wire is what hid #25 for the lifetime of the feature.

    Only the Markdown side can be checked this way: every HTML-native plugin
    Apprise ships (mailto, mailgun, sendgrid, brevo, telegram, …) speaks SMTP
    or a fixed vendor host, so none can be pointed at a local sink. The HTML
    rewrite stays mock-asserted for that reason, not for convenience.
    """

    async def test_markdown_target_receives_the_source_unchanged(self, sink_server):
        sink_server.received.clear()
        encrypted = encrypt_apprise_url(f"json://127.0.0.1:{sink_server.port}/wire")
        body = "```diff\n+ added\n- removed\n```\n"

        result = await dispatch_to_channel(
            apprise_url_encrypted=encrypted, title="wire-title", body=body
        )

        assert result.success is True, result.reason
        assert len(sink_server.received) == 1
        payload = sink_server.received[0]
        assert payload["title"] == "wire-title"
        # Apprise strips trailing whitespace on the way out — the one
        # difference between what the dispatcher hands over and what leaves
        # the process, and invisible to a test that stops at the mock.
        assert payload["message"] == body.rstrip("\n")
        assert "\n".join(payload["message"].splitlines()[1:3]) == "+ added\n- removed"
        assert "<pre" not in payload["message"], "the HTML rewrite must not reach a text target"
