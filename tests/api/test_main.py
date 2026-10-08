"""Tests for src/api/main.py's application-level configuration."""

import logging

import pytest

from src.api.main import app


async def run_lifespan_startup() -> None:
    """Drive one bare ASGI lifespan startup and shutdown through the app.

    FastAPI runs its telemetry auto-configuration inside this exchange, before
    the application's own startup; nothing here touches the database.
    """
    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent: list[dict] = []

    async def receive() -> dict:
        return next(messages)

    async def send(message: dict) -> None:
        sent.append(message)

    await app({"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}, receive, send)
    assert {"type": "lifespan.startup.complete"} in sent


@pytest.mark.asyncio
async def test_otel_environment_does_not_configure_telemetry(monkeypatch, caplog):
    """FastAPI >= 0.142 adds OTLP exporters for spans, metrics and logs —
    exception messages and stack traces included — whenever an OTEL_* endpoint
    is in the environment. On the alert path that must be a decision, not
    something one stray variable switches on (CR 12, #112).

    Without the SDK installed, an attempted auto-configuration fails and FastAPI
    logs it; that log line is the observable proof an attempt was made.
    """
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    with caplog.at_level(logging.WARNING, logger="fastapi"):
        await run_lifespan_startup()
    attempts = [r for r in caplog.records if "automatic telemetry" in r.getMessage()]
    assert not attempts, attempts[0].getMessage()
