"""The test harness must pin DATABASE_URL at the test database.

A pytest run in a shell that sourced /etc/notifier/.env would otherwise leave
DATABASE_URL pointing at production for any code that reads it directly
(issue #22, finding 2; archiver hit this as CannObserv/archiver#157).
"""

import os

from src.core import db_safety


def test_conftest_pins_database_url_to_the_test_database():
    assert os.environ["DATABASE_URL"] == os.environ["TEST_DATABASE_URL"]


def test_pinned_database_url_passes_the_production_guard():
    db_safety.assert_safe_database_url(os.environ["DATABASE_URL"])
