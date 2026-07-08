"""Routing editor, route validation, and mileage fairness logic for L & P Freight."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "lp_dispatch.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_routes_schema() -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
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
        )
    """)
    conn.commit()
    conn.close()


def fetch_routes(load_id: int | None = None) -> pd.DataFrame:
    conn = get_conn()
    q = "SELECT * FROM routes"
    params: tuple[Any, ...] = ()
    if load_id is not None:
        q += " WHERE load_id = ?"
        params = (load_id,)
    q += " ORDER BY id DESC"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def save_route(
    load_id: int,
    waypoints: str,
    planned_loaded_miles: float,
    planned_empty_miles: float,
    google_miles: float | None = None,
    source: str = "planned",
    notes: str = "",
) -> int:
    if google_miles is None:
        google_miles = round(planned_loaded_miles + planned_empty_miles, 1)
    conn = get_conn()
    cursor = conn.execute(
        """
        INSERT INTO routes (load_id, waypoints, planned_loaded_miles, planned_empty_miles, google_miles, source, notes, updated_at)
        VALUES (?,?,?,?,?,?,?,datetime('now'))
        """,
        (load_id, waypoints, planned_loaded_miles, planned_empty_miles, google_miles, source, notes),
    )
    conn.commit()
    rid = int(cursor.lastrowid)
    conn.close()
    return rid


def update_route_actuals(route_id: int, actual_loaded: float, actual_empty: float) -> None:
    conn = get_conn()
    conn.execute(
        """
        UPDATE routes SET actual_loaded_miles = ?, actual_empty_miles = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (actual_loaded, actual_empty, route_id),
    )
    conn.commit()
    conn.close()


def route_variance_analysis(
    planned_loaded: float,
    planned_empty: float,
    actual_loaded: float,
    actual_empty: float,
    google_miles: float | None = None,
    tolerance_pct: float = 10.0,
) -> dict[str, Any]:
    planned_total = planned_loaded + planned_empty
    actual_total = actual_loaded + actual_empty
    basis = google_miles if google_miles and google_miles > 0 else planned_total

    if basis > 0 and actual_total > 0:
        variance = ((actual_total - basis) / basis) * 100.0
    else:
        variance = 0.0

    flagged = abs(variance) > tolerance_pct
    pay_basis = "actual" if flagged else "planned"

    return {
        "planned_total": planned_total,
        "actual_total": actual_total,
        "basis_miles": basis,
        "variance_pct": round(variance, 1),
        "flagged": flagged,
        "tolerance_pct": tolerance_pct,
        "pay_basis": pay_basis,
    }


def last_route_for_load(load_id: int) -> dict[str, Any] | None:
    df = fetch_routes(load_id=load_id)
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def validate_route(
    waypoints: str,
    planned_loaded: float,
    planned_empty: float,
    google_miles: float | None = None,
) -> tuple[bool, str]:
    errors: list[str] = []
    if not waypoints or not waypoints.strip():
        errors.append("Waypoints are required.")
    if planned_loaded < 0:
        errors.append("Planned loaded miles cannot be negative.")
    if planned_empty < 0:
        errors.append("Planned empty miles cannot be negative.")
    if google_miles is not None and google_miles < 0:
        errors.append("Google miles cannot be negative.")
    if planned_loaded + planned_empty <= 0:
        errors.append("Total planned miles must be greater than zero.")
    if google_miles is not None and google_miles > 0:
        expected = round(planned_loaded + planned_empty, 1)
        if abs(google_miles - expected) > expected * 0.25:
            errors.append(
                f"Google miles ({google_miles:.1f}) differs >25% from planned "
                f"({expected:.1f}). Confirm route or use actuals."
            )
    if errors:
        return False, "; ".join(errors)
    return True, "Route is valid."
