"""Tests for the driver-facing view (HOS, loads, accept, BOL capture)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import lp_helpers.database as dbmod
from lp_helpers.driver import (
    get_driver_hos,
    get_driver_loads,
    accept_load,
    save_bol_photo,
)


def _init(tmp_path: Path):
    db = tmp_path / "test_driver.db"
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
            status TEXT, accepted_at TEXT, bol_photo_path TEXT, pickup_date TEXT
        );
        CREATE TABLE po_loads (id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER, status TEXT);
        """
    )
    conn.execute(
        "INSERT INTO loads (id, bol_number, shipper, commodity, origin, destination, total_revenue, status, pickup_date) "
        "VALUES (1,'LP-A','Sibelco','Feldspar','Spruce Pine, NC','GA',5000,'Logged','2026-07-11')"
    )
    conn.execute(
        "INSERT INTO loads (id, bol_number, shipper, commodity, origin, destination, total_revenue, status, pickup_date) "
        "VALUES (2,'LP-B','Covia','Quartz','Spruce Pine, NC','GA',4000,'In Transit','2026-07-10')"
    )
    conn.execute("INSERT INTO po_loads (load_id, status) VALUES (2,'Scheduled')")
    conn.execute("INSERT INTO po_loads (load_id, status) VALUES (1,'Scheduled')")
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


class TestDriverView:
    def test_hos_present(self, db):
        hos = get_driver_hos()
        assert "drive_remaining_hours" in hos
        assert hos["driver_name"]

    def test_loads_split(self, db):
        dv = get_driver_loads()
        assert any(l["bol_number"] == "LP-A" for l in dv["pending"])
        assert any(l["bol_number"] == "LP-B" for l in dv["active"])

    def test_accept_stamps_and_live_billing(self, db):
        accept_load(1)
        conn = dbmod.get_conn()
        row = conn.execute("SELECT status, accepted_at FROM loads WHERE id=1").fetchone()
        po = conn.execute("SELECT status FROM po_loads WHERE load_id=1").fetchone()
        conn.close()
        assert row["status"] == "Accepted"
        assert row["accepted_at"]
        assert po["status"] == "In Transit"  # customer billing live

    def test_accept_idempotent(self, db):
        accept_load(1, "Accepted")
        accept_load(1, "In Transit")  # should NOT overwrite accepted_at
        conn = dbmod.get_conn()
        row = conn.execute("SELECT status, accepted_at FROM loads WHERE id=1").fetchone()
        conn.close()
        assert row["status"] == "Accepted"  # ignored because accepted_at already set

    def test_save_bol_photo(self, db, tmp_path):
        p = save_bol_photo(2, "bol.jpg", b"fakebytes")
        assert Path(p).exists()
        conn = dbmod.get_conn()
        row = conn.execute("SELECT bol_photo_path FROM loads WHERE id=2").fetchone()
        conn.close()
        assert row["bol_photo_path"] == p
