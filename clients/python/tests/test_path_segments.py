"""Caller-supplied IDs reach the server as one escaped path segment (#97).

Every hand-written method used to put its ID straight into an f-string path,
so an ID holding ``/``, ``?``, ``#`` or ``%`` changed which URL was requested:
``channels.delete("x/../templates/y")`` named one resource and hit another.
Every method now quotes with ``safe=""``, as the generated client does. The
generated client also passes a bare ``..`` through (CR 7), which ``segment()``
refuses; its IDs are server-validated ULIDs, so it is left as generated.

A 404 answers every request, so each method raises before parsing a body and
the test reads the path off the one request that went out.
"""

import ast
import re
from pathlib import Path

import httpx
import pytest
import respx

import notifier_client
from notifier_client import NotifierClient, NotifierError, RetryConfig
from notifier_client.paths import segment

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


def _raw_path_lines(source: str) -> list[int]:
    """Lines where an f-string path has a placeholder outside ``segment()``.

    Reads the syntax tree, not the text: Python joins an f-string split
    across lines into one node, and quoting, prefix and layout are gone by
    then, so no spelling of a path escapes the check (CR 10).
    """
    offenders = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.JoinedStr):
            continue
        literal = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
        if not re.search(r"(?:^|/)api/", literal):
            continue
        offenders += [
            v.lineno
            for v in node.values
            if isinstance(v, ast.FormattedValue)
            and not (
                isinstance(v.value, ast.Call)
                and isinstance(v.value.func, ast.Name)
                and v.value.func.id == "segment"
            )
        ]
    return offenders


@pytest.mark.parametrize(
    "line",
    [
        'f"/api/v1/channels/{channel_id}"',
        "f'/api/v1/channels/{channel_id}'",
        'F"/api/v1/channels/{channel_id}"',
        'rf"/api/v1/channels/{channel_id}"',
        'f"api/v1/channels/{channel_id}"',
        'f"/api/v1/channels/{segment(channel_id)}/x/{other}"',
        '(\n    f"/api/v1/channels/"\n    f"{channel_id}/test"\n)',
    ],
)
def test_the_scan_sees_every_spelling_of_a_raw_path(line):
    """CR 8 and CR 10: the line regex missed single-quoted, uppercase and
    relative f-strings, then one split across lines."""
    assert _raw_path_lines(line)


@pytest.mark.parametrize(
    "line",
    [
        'f"/api/v1/channels/{segment(channel_id)}/test"',
        '"/api/v1/channels"',
        'f"expected {model.__name__}"',
    ],
)
def test_the_scan_passes_escaped_and_unrelated_strings(line):
    assert not _raw_path_lines(line)


def test_no_hand_written_path_interpolates_a_raw_value():
    """The table above covers today's methods; this covers tomorrow's. A new
    method that builds ``f"/api/v1/.../{x}"`` without ``segment()`` fails
    here even if nobody adds it to ``CALLS``."""
    package = Path(notifier_client.__file__).parent
    offenders = [
        f"{path.relative_to(package)}:{number}"
        for path in sorted(package.rglob("*.py"))
        if "generated" not in path.parts
        for number in _raw_path_lines(path.read_text())
    ]
    assert offenders == []


@pytest.mark.parametrize("value", ["", ".", ".."])
def test_a_value_that_is_itself_a_dot_segment_is_refused(value):
    """CR 7: dots are unreserved, so quoting leaves ``..`` as is and httpx
    resolves it — ``templates.preview("..")`` requested ``POST /api/v1/preview``,
    another endpoint. No ID or schema name is empty or all dots."""
    with pytest.raises(ValueError, match="path segment"):
        segment(value)


@respx.mock
@pytest.mark.asyncio
async def test_a_dot_segment_id_sends_no_request():
    route = respx.route(host="t.local").mock(return_value=httpx.Response(200, json={}))
    async with NotifierClient(base_url="https://t.local", api_key="nk_x") as c:
        with pytest.raises(ValueError):
            await c.templates.preview("..")
    assert route.call_count == 0
