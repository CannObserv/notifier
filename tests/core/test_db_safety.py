"""Tests for src/core/db_safety.py — production-database refusal.

The parity corpus below encodes the three URL shapes that diverged between
archiver's bash and python implementations (archiver#99, commit ee0c952).
notifier has a single python implementation and ``scripts/dev_server.sh``
calls it, so these exist to keep that single implementation honest.
"""

import pytest

from src.core import db_safety

PARITY_CORPUS = [
    # (url, expected database name)
    ("postgresql://notifier_test", None),  # no ``://`` path — fails closed
    ("notifier_test", None),  # bare name, no scheme — fails closed
    ("postgresql://host/", None),  # no path segment
    ("postgresql://host", None),  # no path at all
    ("postgresql://u:p@host/notifier", "notifier"),
    ("postgresql+asyncpg://u:p@host:5432/notifier", "notifier"),
    # An ``@`` inside the query string is not the credentials delimiter.
    ("postgresql://u:p@host/notifier_test?options=-csearch_path%3Da@b", "notifier_test"),
    ("postgresql://host/notifier_dev#frag", "notifier_dev"),
]


@pytest.mark.parametrize("url,expected", PARITY_CORPUS)
def test_database_name_parity_corpus(url, expected):
    if expected is None:
        with pytest.raises(ValueError):
            db_safety.database_name(url)
    else:
        assert db_safety.database_name(url) == expected


@pytest.mark.parametrize(
    "name,non_prod",
    [
        ("notifier_test", True),
        ("notifier_dev", True),
        ("notifier", False),
        # Suffix, not substring — these are production names.
        ("test_notifier", False),
        ("notifier_testing", False),
        ("notifier_development", False),
    ],
)
def test_is_non_production_uses_suffix_not_substring(name, non_prod):
    assert db_safety.is_non_production(name) is non_prod


def test_assert_safe_allows_test_database(monkeypatch):
    monkeypatch.delenv(db_safety.ALLOW_PROD_ENV_VAR, raising=False)
    db_safety.assert_safe_database_url("postgresql+asyncpg://u@h/notifier_test")


def test_assert_safe_refuses_production_database(monkeypatch):
    monkeypatch.delenv(db_safety.ALLOW_PROD_ENV_VAR, raising=False)
    with pytest.raises(db_safety.ProductionDatabaseError, match="notifier"):
        db_safety.assert_safe_database_url("postgresql+asyncpg://u@h/notifier")


def test_assert_safe_names_the_escape_flag_in_the_message(monkeypatch):
    monkeypatch.delenv(db_safety.ALLOW_PROD_ENV_VAR, raising=False)
    with pytest.raises(db_safety.ProductionDatabaseError, match=db_safety.ALLOW_PROD_ENV_VAR):
        db_safety.assert_safe_database_url("postgresql+asyncpg://u@h/notifier")


def test_assert_safe_allows_production_when_flag_set(monkeypatch):
    monkeypatch.setenv(db_safety.ALLOW_PROD_ENV_VAR, "1")
    db_safety.assert_safe_database_url("postgresql+asyncpg://u@h/notifier")


@pytest.mark.parametrize("value", ["", "0", "true", "yes", "TRUE"])
def test_escape_flag_requires_exact_1(monkeypatch, value):
    """Only ``1`` opts in — a stray truthy string must not open the hole."""
    monkeypatch.setenv(db_safety.ALLOW_PROD_ENV_VAR, value)
    with pytest.raises(db_safety.ProductionDatabaseError):
        db_safety.assert_safe_database_url("postgresql+asyncpg://u@h/notifier")


def test_unparseable_url_fails_closed(monkeypatch):
    """A URL the parser cannot read is refused, not waved through."""
    monkeypatch.delenv(db_safety.ALLOW_PROD_ENV_VAR, raising=False)
    with pytest.raises(db_safety.ProductionDatabaseError):
        db_safety.assert_safe_database_url("notifier_test")


def test_missing_scheme_message_points_at_the_form_not_the_content(monkeypatch):
    """``notifier_test`` is a non-production *name*; only the scheme is missing.

    Refusing is right, but the message must not misdirect toward the URL's
    content when the defect is its form.
    """
    monkeypatch.delenv(db_safety.ALLOW_PROD_ENV_VAR, raising=False)
    with pytest.raises(db_safety.ProductionDatabaseError) as exc:
        db_safety.assert_safe_database_url("notifier_test")
    message = str(exc.value)
    assert "postgresql+asyncpg://" in message
    assert "unreadable" not in message.lower()


def test_error_message_does_not_leak_credentials(monkeypatch):
    monkeypatch.delenv(db_safety.ALLOW_PROD_ENV_VAR, raising=False)
    with pytest.raises(db_safety.ProductionDatabaseError) as exc:
        db_safety.assert_safe_database_url("postgresql://user:hunter2@host/notifier")
    assert "hunter2" not in str(exc.value)
