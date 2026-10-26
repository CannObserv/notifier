"""Tests for src/api/main.py's application-level configuration."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Runs in a fresh interpreter because FastAPI reads FASTAPI_OTEL_AUTO_CONFIGURE
# when FastAPI() is constructed — at import of src.api.main, long before any
# in-process monkeypatch could reach it. Drives one bare ASGI lifespan through
# the notifier app and through a control app built under the same environment,
# and prints how many telemetry attempts each made. Nothing touches the database.
PROBE = """
import asyncio, json, logging
from fastapi import FastAPI
from src.api.main import app

attempts = []

class Keep(logging.Handler):
    def emit(self, record):
        if "automatic telemetry" in record.getMessage():
            attempts.append(record.getMessage())

logging.getLogger("fastapi").addHandler(Keep(level=logging.WARNING))

async def lifespan(target):
    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent = []
    async def receive():
        return next(messages)
    async def send(message):
        sent.append(message)
    await target({"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}, receive, send)
    assert {"type": "lifespan.startup.complete"} in sent, sent
    found = len(attempts)
    attempts.clear()
    return found

print(json.dumps({"app": asyncio.run(lifespan(app)), "control": asyncio.run(lifespan(FastAPI()))}))
"""


def test_otel_environment_does_not_configure_telemetry():
    """FastAPI can add OTLP exporters for spans, metrics and logs — exception
    messages and stack traces included — from OTEL_* endpoints in the
    environment. Since 0.143 that is opt-in, but the opt-in is itself an
    environment variable (FASTAPI_OTEL_AUTO_CONFIGURE), so on the alert path one
    stray variable could still switch it on. It must be a decision (CR 12, #112).

    Without the SDK installed, an attempted auto-configuration fails and FastAPI
    logs it; that log line is the observable proof an attempt was made. The
    control app proves the probe still detects one — a FastAPI release that
    reworded the message or changed the switch would otherwise turn this test
    green by default, as 0.143 did to its in-process predecessor.
    """
    env = {
        **os.environ,
        "FASTAPI_OTEL_AUTO_CONFIGURE": "true",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:9",
    }
    env.pop("OTEL_SDK_DISABLED", None)
    done = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr

    counts = json.loads(done.stdout.strip().splitlines()[-1])

    assert counts["control"] > 0, "probe no longer detects an auto-configuration attempt"
    assert counts["app"] == 0
