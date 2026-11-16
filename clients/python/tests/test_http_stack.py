"""The SDK runs on one HTTP stack, httpx2 (#141).

openapi-python-client 0.30 generates on httpx2, and ``import notifier_client``
loads ``generated/client.py`` through ``generated/__init__.py``, so a
hand-written layer left on httpx would load both stacks on every import.

Checked in a subprocess: ``conftest.py`` calls ``httpx2.alias_httpx()`` so that
respx (httpx-only) can mock httpx2, and that alias would make a stray
``import httpx`` in the SDK resolve to httpx2 in-process and pass unnoticed.
"""

import subprocess
import sys

_PROBE = "import sys, notifier_client; print(' '.join(sorted(sys.modules)))"


def test_importing_the_sdk_loads_httpx2_and_never_httpx():
    out = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE], capture_output=True, text=True, check=True
    ).stdout.split()
    assert "httpx2" in out
    assert not [m for m in out if m.split(".")[0] in ("httpx", "httpcore")]
