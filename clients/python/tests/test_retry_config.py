from notifier_client.retry import RetryConfig


def test_defaults_are_reasonable():
    cfg = RetryConfig()
    assert cfg.max_attempts == 3
    assert cfg.backoff_base == 0.5
    assert cfg.retry_on == frozenset({500, 502, 503, 504})
    assert cfg.honor_retry_after is True


def test_customization():
    cfg = RetryConfig(max_attempts=5, backoff_base=0.1, retry_on={502})
    assert cfg.max_attempts == 5
    assert cfg.retry_on == frozenset({502})
