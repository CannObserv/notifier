"""The environment every notifier subprocess in this suite runs under.

``tenant_credentials`` mints a real key through ``scripts/seed_tenant.py``, and
the app opens the audit channel at import. Both would otherwise write to
journald — ``journalctl -t notifier-keys``, where a test mint of label
``smoke`` is indistinguishable from a production one (#84).
"""

import socket

from tests.conftest import AUDIT_SOCKET_ENV


def test_the_audit_channel_points_at_a_live_sink_not_the_journal(_server_env):
    path = _server_env[AUDIT_SOCKET_ENV]
    assert path != "/dev/log"
    # Reachable, so a subprocess sends there rather than degrading to stderr.
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as probe:
        probe.connect(path)
