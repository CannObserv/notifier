from notifier_client.idempotency import AUTO, resolve_idempotency_key


def test_explicit_value_passthrough():
    assert resolve_idempotency_key("watcher-evt-1") == "watcher-evt-1"


def test_none_returns_none():
    assert resolve_idempotency_key(None) is None


def test_auto_generates_ulid():
    key = resolve_idempotency_key(AUTO)
    assert isinstance(key, str)
    assert len(key) == 26    # ULID canonical form


def test_auto_generates_unique():
    a = resolve_idempotency_key(AUTO)
    b = resolve_idempotency_key(AUTO)
    assert a != b
