"""Tests for the AI Copilot recommendation engine."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import lp_helpers.database as dbmod
from lp_helpers.recommend import get_recommendations, lane_benchmark_rate


def _init(tmp_path: Path):
    db = tmp_path / "test_rec.db"
    old = dbmod.DB_PATH
    dbmod.DB_PATH = db
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE leads (id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT NOT NULL, status TEXT, priority TEXT, last_contact TEXT);
        CREATE TABLE loads (id INTEGER PRIMARY KEY AUTOINCREMENT, bol_number TEXT, shipper TEXT, commodity TEXT, weight_tons REAL, loaded_miles REAL, deadhead_miles REAL, total_revenue REAL, rate_per_ton REAL, status TEXT, pickup_date TEXT, destination TEXT);
        """
    )
    conn.execute("INSERT INTO leads (id, company, status, priority, last_contact) VALUES (1,'Sibelco','Hot','High','2026-01-01')")
    # High-deadhead active load -> backhaul suggestion
    conn.execute(
        "INSERT INTO loads (id, bol_number, shipper, commodity, weight_tons, loaded_miles, deadhead_miles, total_revenue, rate_per_ton, status, pickup_date) "
        "VALUES (1,'LP-A','Covia','Quartz',20,200,300,3000,40,'In Transit','2026-07-01')"
    )
    # Logged load quoted below benchmark -> rate suggestion
    conn.execute(
        "INSERT INTO loads (id, bol_number, shipper, commodity, weight_tons, loaded_miles, deadhead_miles, total_revenue, rate_per_ton, status, pickup_date) "
        "VALUES (2,'LP-B','Trimac','Feldspar',22,285,0,1000,20,'Logged','2026-07-10')"
    )
    # Thin-margin load -> margin suggestion
    conn.execute(
        "INSERT INTO loads (id, bol_number, shipper, commodity, weight_tons, loaded_miles, deadhead_miles, total_revenue, rate_per_ton, status, pickup_date) "
        "VALUES (3,'LP-C','K-T','Mica',10,100,20,800,40,'Delivered','2026-07-02')"
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


class TestRecommend:
    def test_backhaul_suggestion(self, db):
        recs = get_recommendations()
        assert any(r["id"].startswith("backhaul:") for r in recs)

    def test_rate_suggestion(self, db):
        recs = get_recommendations()
        assert any(r["id"].startswith("rate:") for r in recs)

    def test_next_best_lead(self, db):
        recs = get_recommendations()
        assert any(r["id"].startswith("lead:") and "Sibelco" in r["title"] for r in recs)

    def test_sorted_by_severity(self, db):
        recs = get_recommendations()
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sevs = [order.get(r["severity"], 9) for r in recs]
        assert sevs == sorted(sevs)

    def test_lane_benchmark(self, db):
        b = lane_benchmark_rate(22, 285, "Feldspar")
        assert b["rate_per_ton"] > 0
        assert b["revenue"] == pytest.approx(22 * b["rate_per_ton"], 0.5)
