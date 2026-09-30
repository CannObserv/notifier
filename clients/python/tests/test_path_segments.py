"""Caller-supplied IDs reach the server as one escaped path segment (#97).

Every hand-written method used to put its ID straight into an f-string path,
so an ID holding ``/``, ``?``, ``#`` or ``%`` changed which URL was requested:
``channels.delete("x/../templates/y")`` named one resource and hit another.
The generated client never had the bug; it quotes with ``safe=""``, and so
does every method here now.

A 404 answers every request, so each method raises before parsing a body and
the test reads the path off the one request that went out.
"""

import re
from pathlib import Path

import httpx
import pytest
import respx

import notifier_client
from notifier_client import NotifierClient, NotifierError, RetryConfig

HOSTILE = "a/../b?c=1#d %"
ESCAPED = "a%2F..%2Fb%3Fc%3D1%23d%20%25"

CALLS = [
    ("channels.get", lambda c: c.channels.get(HOSTILE), f"/api/v1/channels/{ESCAPED}"),
    (
        "channels.update",
        lambda c: c.channels.update(HOSTILE, name="n"),
        f"/api/v1/channels/{ESCAPED}",
    ),
    ("channels.delete", lambda c: c.channels.delete(HOSTILE), f"/api/v1/channels/{ESCAPED}"),
    (
        "channels.send_test",
        lambda c: c.channels.send_test(HOSTILE),
        f"/api/v1/channels/{ESCAPED}/test",
    ),
    ("templates.get", lambda c: c.templates.get(HOSTILE), f"/api/v1/templates/{ESCAPED}"),
    (
        "templates.update",
        lambda c: c.templates.update(HOSTILE, name="n"),
        f"/api/v1/templates/{ESCAPED}",
    ),
    ("templates.delete", lambda c: c.templates.delete(HOSTILE), f"/api/v1/templates/{ESCAPED}"),
    (
        "templates.preview",
        lambda c: c.templates.preview(HOSTILE),
        f"/api/v1/templates/{ESCAPED}/preview",
    ),
    (
        "apprise.get_plugin",
        lambda c: c.apprise.get_plugin(HOSTILE),
        f"/api/v1/apprise/plugins/{ESCAPED}",
    ),
    (
        "apprise.assemble",
        lambda c: c.apprise.assemble(HOSTILE, tokens={}),
        f"/api/v1/apprise/plugins/{ESCAPED}/assemble",
    ),
    ("monitors.get", lambda c: c.monitors.get(HOSTILE), f"/api/v1/monitors/{ESCAPED}"),
    (
        "monitors.update",
        lambda c: c.monitors.update(HOSTILE, name="n"),
        f"/api/v1/monitors/{ESCAPED}",
    ),
    ("monitors.delete", lambda c: c.monitors.delete(HOSTILE), f"/api/v1/monitors/{ESCAPED}"),
    (
        "monitors.checkin",
        lambda c: c.monitors.checkin(HOSTILE),
        f"/api/v1/monitors/{ESCAPED}/checkin",
    ),
    ("redeliver", lambda c: c.redeliver(HOSTILE), f"/api/v1/dispatch/{ESCAPED}/redeliver"),
]


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "call", "path"), CALLS, ids=[c[0] for c in CALLS])
async def test_an_id_is_sent_as_one_escaped_segment(name, call, path):
    route = respx.route(host="t.local").mock(return_value=httpx.Response(404))
    async with NotifierClient(
        base_url="https://t.local",
        api_key="nk_x",
        retry_config=RetryConfig(max_attempts=1, backoff_base=0.0),
    ) as c:
        with pytest.raises(NotifierError):
            await call(c)

    url = route.calls.last.request.url
    assert url.raw_path.decode() == path
    assert url.query == b""
    assert url.fragment == ""


def test_no_hand_written_path_interpolates_a_raw_value():
    """The table above covers today's methods; this covers tomorrow's. A new
    method that builds ``f"/api/v1/.../{x}"`` without ``segment()`` fails
    here even if nobody adds it to ``CALLS``."""
    package = Path(notifier_client.__file__).parent
    raw = re.compile(r'f"/[^"]*\{(?!segment\()[^}]*\}')
    offenders = [
        f"{path.relative_to(package)}:{number}: {line.strip()}"
        for path in sorted(package.rglob("*.py"))
        if "generated" not in path.parts
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if raw.search(line)
    ]
    assert offenders == []
