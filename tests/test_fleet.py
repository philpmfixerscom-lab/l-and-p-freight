"""Tests for the live fleet view (telemetry + active loads + deadhead watch)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import lp_helpers.database as dbmod
from lp_helpers.fleet import get_fleet_view, ACTIVE_STATUSES


def _init(tmp_path: Path):
    db = tmp_path / "test_fleet.db"
    old = dbmod.DB_PATH
    dbmod.DB_PATH = db
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE loads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bol_number TEXT, shipper TEXT, commodity TEXT,
            origin TEXT, destination TEXT,
            loaded_miles REAL, deadhead_miles REAL, total_revenue REAL,
            status TEXT, pickup_date TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO loads (bol_number, shipper, commodity, origin, destination, loaded_miles, deadhead_miles, total_revenue, status) "
        "VALUES ('LP-A','Sibelco','Feldspar','Spruce Pine, NC','GA', 300, 60, 5000, 'In Transit')"
    )
    conn.execute(
        "INSERT INTO loads (bol_number, shipper, commodity, origin, destination, loaded_miles, deadhead_miles, total_revenue, status) "
        "VALUES ('LP-B','Covia','Quartz','Spruce Pine, NC','GA', 200, 200, 4000, 'Accepted')"
    )
    # Logged load should NOT appear in the active view
    conn.execute(
        "INSERT INTO loads (bol_number, shipper, commodity, origin, destination, loaded_miles, deadhead_miles, total_revenue, status) "
        "VALUES ('LP-C','Trimac','Mica','Spruce Pine, NC','GA', 250, 10, 3000, 'Logged')"
    )
    conn.commit()
    conn.close()
    return old


@pytest.fixture()
def db(tmp_path: Path):
    old = _init(tmp_path)
    try:
        yield
    finally:
        dbmod.DB_PATH = old


class TestFleetView:
    def test_vehicle_telemetry(self, db):
        fv = get_fleet_view()
        assert fv["vehicle"]["vehicle_id"]
        assert fv["vehicle"]["status"] in ("Moving", "Idle")
        assert "speed_mph" in fv["vehicle"]

    def test_active_loads_excludes_logged(self, db):
        fv = get_fleet_view()
        bols = [l["bol_number"] for l in fv["active_loads"]]
        assert "LP-A" in bols
        assert "LP-B" in bols
        assert "LP-C" not in bols  # Logged is not active

    def test_deadhead_watch_flags_high_share(self, db):
        fv = get_fleet_view()
        # LP-B is 50% deadhead -> should be flagged
        watched = [w["bol_number"] for w in fv["deadhead_watch"]]
        assert "LP-B" in watched
        assert "LP-A" not in watched  # 60/360 = 17% -> under 35% threshold
