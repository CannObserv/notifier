"""Monitors left notifier for co-status (#83), and must not come back.

Notifier publishes what consumers send; it does not originate alerts. The
dead-man's timers were the one exception, and CannObserv/status took them over
on 2026-09-28. These tests fail if any piece of the old machinery reappears:
a route, the model, the table, the sweep units or their scripts.
"""

from pathlib import Path

from src.api.main import app
from src.core.models import Base
from src.core.tenants import TenantInventory

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_monitor_route_is_served():
    paths = app.openapi()["paths"]
    assert not [p for p in paths if "monitor" in p]


async def test_a_checkin_is_not_found(client):
    response = await client.post(
        "/api/v1/monitors/01J0000000000000000000M0N1/checkin", json={"status": "ok"}
    )
    assert response.status_code == 404


def test_no_monitors_table_in_the_model():
    assert "monitors" not in Base.metadata.tables


def test_the_tenant_inventory_counts_no_monitors():
    assert "monitors" not in TenantInventory.__dataclass_fields__


def test_no_sweep_units_or_scripts_ship():
    leftovers = [
        *(REPO_ROOT / "deploy").glob("notifier-sweep*"),
        REPO_ROOT / "scripts" / "sweep.sh",
        REPO_ROOT / "scripts" / "sweep_monitors.py",
    ]
    assert [p.name for p in leftovers if p.exists()] == []
