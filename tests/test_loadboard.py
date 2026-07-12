"""Tests for the Load Board (fetch, filter, assign)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import lp_helpers.database as dbmod
from lp_helpers.loadboard import (
    fetch_board_loads,
    filter_board,
    assign_load,
    board_status_options,
)


def _init(tmp_path: Path):
    db = tmp_path / "test_board.db"
    old = dbmod.DB_PATH
    dbmod.DB_PATH = db
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE loads (id INTEGER PRIMARY KEY AUTOINCREMENT, bol_number TEXT, shipper TEXT, commodity TEXT, origin TEXT, destination TEXT, weight_tons REAL, loaded_miles REAL, deadhead_miles REAL, total_revenue REAL, rate_per_ton REAL, status TEXT, pickup_date TEXT, accepted_at TEXT);
        CREATE TABLE po_loads (id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER, status TEXT);
        """
    )
    conn.execute("INSERT INTO loads (id, bol_number, shipper, commodity, origin, destination, total_revenue, status) VALUES (1,'LP-A','Sibelco','Feldspar','Spruce Pine, NC','GA',5000,'Logged')")
    conn.execute("INSERT INTO loads (id, bol_number, shipper, commodity, origin, destination, total_revenue, status) VALUES (2,'LP-B','Covia','Quartz','Spruce Pine, NC','GA',4000,'Accepted')")
    conn.execute("INSERT INTO loads (id, bol_number, shipper, commodity, origin, destination, total_revenue, status) VALUES (3,'LP-C','Sibelco','Mica','Spruce Pine, NC','GA',3000,'Logged')")
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


class TestLoadBoard:
    def test_fetch_all(self, db):
        loads = fetch_board_loads()
        assert len(loads) == 3

    def test_filter_by_status(self, db):
        loads = fetch_board_loads()
        logged = filter_board(loads, status="Logged")
        assert len(logged) == 2
        assert all(l["status"] == "Logged" for l in logged)

    def test_filter_by_shipper(self, db):
        loads = fetch_board_loads()
        sib = filter_board(loads, shipper="Sibelco")
        assert len(sib) == 2

    def test_search_query(self, db):
        loads = fetch_board_loads()
        res = filter_board(loads, query="LP-B")
        assert len(res) == 1 and res[0]["bol_number"] == "LP-B"

    def test_assign_marks_accepted_and_invoices(self, db):
        assign_load(1, "Kohler")
        conn = dbmod.get_conn()
        row = conn.execute("SELECT status, accepted_at, notes FROM loads WHERE id=1").fetchone()
        inv = conn.execute("SELECT 1 FROM invoices WHERE load_id=1").fetchone()
        conn.close()
        assert row["status"] == "Accepted"
        assert row["accepted_at"]
        assert inv is not None

    def test_options(self, db):
        loads = fetch_board_loads()
        assert "All" in board_status_options(loads)
        assert "Sibelco" in board_status_options(loads)
