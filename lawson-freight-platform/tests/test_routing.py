"""Unit tests for L & P Freight routing, mileage fairness, and driver pay calculation."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from routing_editor import (
    route_variance_analysis,
    validate_route,
    save_route,
    update_route_actuals,
    fetch_routes,
    init_routes_schema,
    last_route_for_load,
)


def _init_test_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_routing.db"
    import routing_editor as mod
    old_db = mod.DB_PATH
    mod.DB_PATH = db
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS loads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bol_number TEXT,
            shipper TEXT,
            commodity TEXT,
            loaded_miles REAL,
            empty_miles REAL,
            pickup_date TEXT,
            origin TEXT,
            destination TEXT,
            rate_per_ton REAL,
            total_revenue REAL,
            notes TEXT,
            asset_id INTEGER,
            route_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS routes (
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
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (load_id) REFERENCES loads(id)
        );
        """
    )
    conn.execute(
        "INSERT INTO loads (id, bol_number, shipper) VALUES (1, 'LP-TEST-1', 'Sibelco')"
    )
    conn.commit()
    conn.close()
    try:
        yield db
    finally:
        mod.DB_PATH = old_db


@pytest.fixture()
def test_db(tmp_path: Path):
    yield from _init_test_db(tmp_path)


class TestRouteVarianceAnalysis:
    def test_no_variance(self):
        result = route_variance_analysis(280, 285, 280, 285)
        assert result["variance_pct"] == 0.0
        assert result["flagged"] is False
        assert result["pay_basis"] == "planned"

    def test_high_variance_flags(self):
        result = route_variance_analysis(280, 285, 360, 285)
        assert result["variance_pct"] == pytest.approx(13.4, 0.1)
        assert result["flagged"] is True
        assert result["pay_basis"] == "actual"

    def test_google_basis_used(self):
        result = route_variance_analysis(280, 285, 360, 285, google_miles=565)
        assert result["basis_miles"] == 565
        assert result["variance_pct"] == pytest.approx(round((645 - 565) / 565 * 100, 1), 1)

    def test_variance_negative(self):
        result = route_variance_analysis(300, 300, 260, 260)
        assert result["variance_pct"] == pytest.approx(-13.3, 0.1)
        assert result["flagged"] is True


class TestDriverPayCalc:
    def calcpay(self, loaded_miles, empty_miles, loaded_rate, empty_rate,
                bonuses=0.0, deductions=0.0, accessorials=0.0):
        total = (loaded_miles * loaded_rate) + (empty_miles * empty_rate) + bonuses + accessorials - deductions
        return round(total, 2)

    def test_basic_pay(self):
        assert self.calcpay(280, 285, 1.75, 0.85) == pytest.approx(732.25)

    def test_with_bonuses_and_deductions(self):
        pay = self.calcpay(280, 285, 1.75, 0.85, bonuses=100.0, deductions=25.0)
        assert pay == pytest.approx(807.25)

    def test_no_empty_miles(self):
        assert self.calcpay(300, 0, 1.80, 0.90) == pytest.approx(540.0)


class TestValidateRoute:
    def test_valid_route(self):
        ok, msg = validate_route("Spruce Pine -> Nashville -> GA", 280, 285, google_miles=565)
        assert ok is True
        assert "valid" in msg.lower()

    def test_missing_waypoints(self):
        ok, msg = validate_route("", 280, 285)
        assert ok is False
        assert "waypoints" in msg.lower()

    def test_negative_miles(self):
        ok, msg = validate_route("A -> B", -10, 20)
        assert ok is False
        assert "negative" in msg.lower()

    def test_google_miles_too_different(self):
        ok, msg = validate_route("A -> B", 280, 285, google_miles=900)
        assert ok is False
        assert "25%" in msg


class TestRouteLifecycle:
    def test_save_and_fetch(self, test_db):
        rid = save_route(1, "SP -> Nash -> GA", 280.0, 285.0, google_miles=565.0)
        assert rid > 0
        df = fetch_routes(load_id=1)
        assert len(df) == 1
        assert df.iloc[0]["planned_loaded_miles"] == 280.0

    def test_update_actuals(self, test_db):
        rid = save_route(1, "SP -> Nash -> GA", 280.0, 285.0, google_miles=565.0)
        update_route_actuals(rid, 310.0, 290.0)
        df = fetch_routes(load_id=1)
        assert df.iloc[0]["actual_loaded_miles"] == 310.0
        assert df.iloc[0]["actual_empty_miles"] == 290.0

    def test_last_route_for_load(self, test_db):
        save_route(1, "SP -> Nash", 280.0, 285.0)
        save_route(1, "SP -> I-40 -> Nash", 300.0, 275.0)
        last = last_route_for_load(1)
        assert last is not None
        assert last["waypoints"] == "SP -> I-40 -> Nash"


class TestMileageFairness:
    def test_pay_planned_when_within_tolerance(self):
        result = route_variance_analysis(280, 285, 290, 285)
        assert result["flagged"] is False
        assert result["pay_basis"] == "planned"

    def test_pay_actual_when_outside_tolerance(self):
        result = route_variance_analysis(280, 285, 420, 285)
        assert result["flagged"] is True
        assert result["pay_basis"] == "actual"

    def test_exact_threshold(self):
        result = route_variance_analysis(280, 285, 308.5, 285, tolerance_pct=10.0)
        assert result["variance_pct"] == round((593.5 - 565) / 565 * 100, 1)
        assert result["flagged"] is False
        assert result["pay_basis"] == "planned"
