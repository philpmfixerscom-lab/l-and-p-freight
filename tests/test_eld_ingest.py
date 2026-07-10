"""Tests for ELD/hardware mileage ingestion into routes (feeds driver pay)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import routing_editor as mod
from routing_editor import (
    ingest_eld_miles,
    create_eld_webhook,
    fetch_routes,
    save_route,
)


def _init_test_db(tmp_path: Path):
    db = tmp_path / "test_eld.db"
    old_db = mod.DB_PATH
    mod.DB_PATH = db
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE loads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bol_number TEXT, shipper TEXT, loaded_miles REAL, deadhead_miles REAL
        );
        CREATE TABLE routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            load_id INTEGER NOT NULL,
            waypoints TEXT NOT NULL,
            planned_loaded_miles REAL NOT NULL,
            planned_empty_miles REAL NOT NULL,
            google_miles REAL,
            actual_loaded_miles REAL,
            actual_empty_miles REAL,
            source TEXT DEFAULT 'planned',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute("INSERT INTO loads (id, bol_number, shipper, loaded_miles, deadhead_miles) VALUES (1,'LP-ELD-1','Sibelco',280,285)")
    conn.commit()
    conn.close()
    try:
        yield db
    finally:
        mod.DB_PATH = old_db


@pytest.fixture()
def test_db(tmp_path: Path):
    yield from _init_test_db(tmp_path)


class TestIngestEldMiles:
    def test_creates_route_when_none(self, test_db):
        res = ingest_eld_miles(1, 310, 285)
        assert res["route_created"] is True
        assert res["actual_total_miles"] == 595
        df = fetch_routes(load_id=1)
        assert df.iloc[0]["actual_loaded_miles"] == 310
        assert df.iloc[0]["source"] == "eld"

    def test_updates_existing_route(self, test_db):
        rid = save_route(1, "SP -> GA", 280, 285, google_miles=565)
        res = ingest_eld_miles(1, 300, 275)
        assert res["route_created"] is False
        assert res["route_id"] == rid
        df = fetch_routes(load_id=1)
        assert df.iloc[0]["actual_loaded_miles"] == 300
        assert df.iloc[0]["actual_empty_miles"] == 275

    def test_negative_clamped(self, test_db):
        res = ingest_eld_miles(1, -5, -10)
        assert res["actual_total_miles"] == 0


class TestEldWebhook:
    def test_miles_update_ingested(self, test_db):
        out = create_eld_webhook({
            "provider": "samsara",
            "event": "trip_completed",
            "load_id": 1,
            "data": {"actual_loaded_miles": 320, "actual_empty_miles": 290},
        })
        assert out["status"] == "ingested"
        df = fetch_routes(load_id=1)
        assert df.iloc[0]["actual_loaded_miles"] == 320

    def test_unknown_event_accepted(self, test_db):
        out = create_eld_webhook({"provider": "motive", "event": "heartbeat", "load_id": 1})
        assert out["status"] == "accepted"

    def test_missing_load_id_accepted(self, test_db):
        out = create_eld_webhook({"event": "miles_update", "data": {"actual_loaded_miles": 100}})
        assert out["status"] == "accepted"
