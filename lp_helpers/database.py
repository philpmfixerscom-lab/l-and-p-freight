"""SQLite persistence layer for L & P Dispatch v3.0 — local-first Freight OS."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from lp_helpers.load_board import ensure_opportunities_table

BASE_DIR = Path(__file__).resolve().parent.parent
_DATA_ROOT = Path(os.environ.get("LP_DATA_DIR", str(BASE_DIR)))
DB_PATH = _DATA_ROOT / "lp_dispatch.db"
ATTACHMENTS_DIR = _DATA_ROOT / "attachments"
LAWSON_DB = BASE_DIR / "lawson_freight.db"
LP_FREIGHT_DB = BASE_DIR / "lp_freight.db"

DEMO_MODE_KEY = "demo_mode_active"
NIGHT_MODE_KEY = "night_driving_mode"
OWNER_ROLE_KEY = "owner_role"
MIGRATION_SETTING_KEY = "legacy_migration_v1"
MIGRATION_REPORT_KEY = "legacy_migration_report"
MIGRATION_BANNER_KEY = "legacy_migration_pending_banner"

APP_VERSION = "3.0"
TRAILER_FT = 39
TRAILER_MAX_TONS = 24
TRAILER_PROFILE = "39ft / 24-ton Frameless lined end-dump"

PRIMARY_LANE: dict[str, Any] = {
    "origin": "Spruce Pine, NC",
    "destination": "Central Georgia (Kohler area)",
    "loaded_miles": 285,
    "baseline_rate_per_ton": 48.0,
}

COMMODITY_OPTIONS: list[str] = [
    "Feldspar",
    "Mica",
    "Spar",
    "Clay",
    "Rock",
    "Lime",
    "Fertilizer",
    "Sand",
    "Gravel",
    "Aggregate",
    "Other",
]

SEED_LEADS: list[dict[str, Any]] = [
    {
        "company": "Sibelco",
        "contact_name": "Dispatch",
        "phone": "828-592-2780",
        "commodity_focus": "Feldspar, Mica",
        "lane_notes": "Spruce Pine quarry — priority shipper",
        "status": "Hot",
        "priority": 1,
    },
    {
        "company": "Covia",
        "contact_name": "Dispatch",
        "phone": "1-800-243-9004",
        "commodity_focus": "Feldspar, Clay",
        "lane_notes": "National miner — NC/GA lanes",
        "status": "Hot",
        "priority": 2,
    },
    {
        "company": "K-T Feldspar",
        "contact_name": "Dispatch",
        "phone": "828-765-9621",
        "commodity_focus": "Feldspar",
        "lane_notes": "Local Spruce Pine shipper",
        "status": "Hot",
        "priority": 3,
    },
    {
        "company": "Trimac",
        "contact_name": "Dispatch",
        "phone": "828-765-7491",
        "commodity_focus": "Bulk / brokered",
        "lane_notes": "Broker / carrier partner",
        "status": "Hot",
        "priority": 4,
    },
]

SEED_COMPLIANCE: list[tuple[str, str, str | None, str]] = [
    ("USDOT / MC authority — L & P", "Verify", "2027-06-30", "Confirm interstate authority before hauling."),
    ("Liability & cargo insurance", "Verify", "2027-01-15", "Confirm limits, cargo exclusions, cert holders."),
    ("UCR registration", "Pending", "2026-12-31", "Annual interstate registration."),
    ("ELD / HOS records", "Active", None, "Retain ELD records if required for operation."),
    ("Drug & alcohol consortium", "Required", "2026-09-01", "CDL interstate requirement."),
    ("Annual tractor inspection", "Due Soon", "2026-08-15", "Keep proof in cab."),
    ("39ft end-dump trailer inspection", "Due Soon", "2026-08-15", "Lined end-dump annual inspection."),
    ("Driver qualification file", "In Progress", None, "CDL, med card, MVR, road test."),
    ("Load securement / tarp — bulk fines", "Active", None, "Cover and secure feldspar, mica, clay fines."),
    ("IFTA fuel tax reporting", "Active", "2026-07-31", "Quarterly IFTA — import fuel CSV here."),
]

SEED_GEOFENCES: list[dict[str, Any]] = [
    {
        "name": "Spruce Pine Yard",
        "location_label": "L & P Yard — Spruce Pine NC",
        "geofence_type": "Yard",
        "latitude": 35.912,
        "longitude": -82.064,
        "radius_m": 800.0,
        "notes": "Depart / return point — deadhead baseline.",
    },
    {
        "name": "Kohler Central GA",
        "location_label": "Kohler area delivery zone — Central GA",
        "geofence_type": "Delivery",
        "latitude": 32.98,
        "longitude": -82.72,
        "radius_m": 5000.0,
        "notes": "Primary delivery geofence — log arrivals for loaded-mile credit.",
    },
]

GEO_POSITION_PRESETS: dict[str, tuple[float, float]] = {
    "Spruce Pine Yard": (35.912, -82.064),
    "Kohler Central GA": (32.98, -82.72),
}

_DEMO_LOADS: tuple[tuple[str, str, float, float, float, int], ...] = (
    ("Sibelco", "Feldspar", 24, 285, 285, 7),
    ("Covia", "Clay", 23, 290, 285, 14),
    ("K-T Feldspar", "Mica", 22, 285, 280, 21),
    ("Sibelco", "Feldspar", 24, 285, 285, 3),
    ("Trimac", "Aggregate", 24, 310, 295, 10),
    ("Covia", "Feldspar", 23, 285, 275, 18),
    ("Sibelco", "Spar", 24, 285, 285, 1),
    ("K-T Feldspar", "Clay", 22, 290, 285, 25),
    ("Covia", "Feldspar", 24, 285, 285, 5),
    ("Sibelco", "Feldspar", 23, 285, 270, 12),
    ("Trimac", "Rock", 24, 300, 290, 28),
    ("Covia", "Mica", 22, 285, 285, 8),
)

_DEMO_FUEL: tuple[tuple[int, float, float, float, str], ...] = (
    (5, 120, 380.0, 145000, "NC"),
    (12, 118, 300.0, 144680, "GA"),
    (28, 125, 395.0, 144200, "SC"),
    (45, 110, 360.0, 143750, "NC"),
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    contact_name TEXT,
    phone TEXT,
    email TEXT,
    commodity_focus TEXT,
    lane_notes TEXT,
    status TEXT DEFAULT 'Active',
    priority INTEGER DEFAULT 5,
    last_contact TEXT,
    next_followup_date TEXT,
    followup_type TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS loads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bol_number TEXT UNIQUE,
    shipper TEXT,
    commodity TEXT,
    weight_tons REAL,
    miles REAL,
    loaded_miles REAL,
    deadhead_miles REAL,
    pickup_date TEXT,
    delivery_date TEXT,
    origin TEXT,
    destination TEXT,
    rate_per_ton REAL,
    total_revenue REAL,
    status TEXT DEFAULT 'Logged',
    accepted_at TEXT,
    bol_photo_path TEXT,
    notes TEXT,
    voice_audio_path TEXT,
    lead_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    call_type TEXT,
    notes TEXT,
    outcome TEXT,
    voice_audio_path TEXT,
    duration_sec INTEGER,
    logged_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS compliance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item TEXT NOT NULL,
    status TEXT,
    due_date TEXT,
    notes TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS telematics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT,
    odometer REAL,
    engine_hours REAL,
    latitude REAL,
    longitude REAL,
    speed_mph REAL,
    fuel_level_pct REAL,
    notes TEXT,
    imported_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fuel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fill_date TEXT,
    gallons REAL,
    cost REAL,
    odometer REAL,
    state TEXT,
    vendor TEXT,
    notes TEXT,
    imported_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS maintenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT,
    task TEXT,
    status TEXT DEFAULT 'Scheduled',
    due_date TEXT,
    completed_date TEXT,
    odometer REAL,
    cost REAL,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ai_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    title TEXT,
    detail TEXT,
    priority TEXT,
    dismissed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS geofences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location_label TEXT,
    geofence_type TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    radius_m REAL NOT NULL,
    notes TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS geofence_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    geofence_name TEXT NOT NULL,
    distance_m REAL,
    latitude REAL,
    longitude REAL,
    load_id INTEGER,
    logged_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (load_id) REFERENCES loads(id)
);

CREATE TABLE IF NOT EXISTS sms_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    alert_type TEXT,
    message TEXT,
    sent_via TEXT DEFAULT 'clipboard',
    twilio_sid TEXT,
    logged_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT DEFAULT 'manual',
    lane TEXT NOT NULL,
    commodity TEXT,
    rate TEXT,
    contact TEXT,
    notes TEXT,
    status TEXT DEFAULT 'Open',
    created_at TEXT DEFAULT (datetime('now')),
    refreshed_at TEXT
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    loaded_rate_per_mile REAL NOT NULL DEFAULT 0.0,
    empty_rate_per_mile REAL NOT NULL DEFAULT 0.0,
    status TEXT DEFAULT 'Active',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    load_id INTEGER NOT NULL,
    asset_id INTEGER,
    driver_name TEXT,
    planned_loaded_miles REAL NOT NULL,
    actual_loaded_miles REAL NOT NULL,
    planned_empty_miles REAL NOT NULL,
    actual_empty_miles REAL NOT NULL,
    loaded_rate REAL NOT NULL,
    empty_rate REAL NOT NULL,
    bonuses REAL DEFAULT 0.0,
    deductions REAL DEFAULT 0.0,
    accessorials REAL DEFAULT 0.0,
    total_pay REAL NOT NULL,
    variance_pct REAL,
    status TEXT DEFAULT 'Draft',
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (load_id) REFERENCES loads(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
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

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact_name TEXT,
    phone TEXT,
    email TEXT,
    api_key TEXT UNIQUE,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    po_number TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'Open',
    total_estimated_revenue REAL DEFAULT 0.0,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS po_loads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id INTEGER NOT NULL,
    load_id INTEGER,
    sequence INTEGER DEFAULT 1,
    scheduled_pickup_date TEXT,
    scheduled_delivery_date TEXT,
    status TEXT DEFAULT 'Scheduled',
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (po_id) REFERENCES purchase_orders(id),
    FOREIGN KEY (load_id) REFERENCES loads(id)
);

CREATE TABLE IF NOT EXISTS eld_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,
    payload TEXT,
    logged_at TEXT DEFAULT (datetime('now'))
);
"""


def get_conn() -> sqlite3.Connection:
    """Return a SQLite connection with Row factory (safe for Streamlit threading)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def clear_cache() -> None:
    """Clear Streamlit data cache for decorated fetch helpers."""
    try:
        st.cache_data.clear()
    except Exception:
        pass


def get_setting(key: str, default: str = "") -> str:
    """Read a string value from app_settings."""
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
    if row is None or row["value"] is None:
        return default
    return str(row["value"])


def set_setting(key: str, value: str) -> None:
    """Upsert a string value into app_settings."""
    with closing(get_conn()) as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now')
            """,
            (key, value),
        )
        conn.commit()
    clear_cache()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _legacy_conn(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _lead_id_by_company(conn: sqlite3.Connection, company: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM leads WHERE company = ?",
        (company,),
    ).fetchone()
    return int(row["id"]) if row else None


def _normalize_bol(bol: str | None, fallback_id: int | str) -> str:
    """Remap legacy LAW- / LF prefixes to LP- for L & P Dispatch."""
    bol_s = (bol or "").strip()
    if not bol_s:
        return f"LP-MIG-LF{fallback_id}"
    upper = bol_s.upper()
    if upper.startswith("LAW-"):
        return "LP-" + bol_s[4:]
    if upper.startswith("LF"):
        return f"LP-MIG-{bol_s}"
    return bol_s


def calculate_rate(
    weight_tons: float,
    miles: float,
    loaded_miles: float | None = None,
    commodity: str = "",
) -> tuple[float, float]:
    """Rule-based rate from baseline $/ton and loaded-mile efficiency."""
    base = float(PRIMARY_LANE["baseline_rate_per_ton"])
    lm = loaded_miles if loaded_miles and loaded_miles > 0 else miles
    loaded_share = lm / miles if miles > 0 else 1.0

    if loaded_share >= 0.95:
        multiplier = 1.05
    elif loaded_share >= 0.85:
        multiplier = 1.02
    elif loaded_share < 0.70:
        multiplier = 0.95
    else:
        multiplier = 1.0

    commodity_lower = commodity.lower()
    if any(token in commodity_lower for token in ("feldspar", "mica", "spar", "clay", "quartz")):
        multiplier *= 1.02
    elif "fertilizer" in commodity_lower:
        multiplier *= 1.03
    elif "lime" in commodity_lower:
        multiplier *= 1.01

    rate = round(base * multiplier, 2)
    revenue = round(rate * weight_tons, 2)
    return rate, revenue


def generate_bol_number() -> str:
    """Generate BOL id: LP-YYYYMMDD-XXXXXX."""
    stamp = datetime.now().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"LP-{stamp}-{suffix}"


_ALLOWED_TABLES = {
    "loads", "leads", "fuel", "telematics", "geofence_events", "call_logs",
    "maintenance", "sms_log", "compliance", "ai_suggestions", "app_settings",
    "assets", "settlements", "routes", "customers", "purchase_orders", "po_loads",
    "eld_events",
}


def _copy_simple_table(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    table: str,
    *,
    dedupe_sql: str | None = None,
    dedupe_args_fn: Any = None,
) -> int:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Table '{table}' is not in the allowlist.")
    if not _table_exists(src, table) or not _table_exists(dst, table):
        return 0

    dst_cols = [row[1] for row in dst.execute(f'PRAGMA table_info("{table}")').fetchall()]
    src_cols = [row[1] for row in src.execute(f'PRAGMA table_info("{table}")').fetchall()]
    common = [c for c in dst_cols if c in src_cols]
    if not common:
        return 0

    rows = src.execute(f'SELECT {", ".join(common)} FROM "{table}"').fetchall()
    inserted = 0
    col_sql = ", ".join(common)
    placeholders = ", ".join("?" for _ in common)

    for row in rows:
        payload = {k: row[k] for k in common}
        if dedupe_sql and dedupe_args_fn:
            args = dedupe_args_fn(payload)
            if args and dst.execute(dedupe_sql, args).fetchone():
                continue
        dst.execute(
            f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders})',
            tuple(payload[c] for c in common),
        )
        inserted += 1
    return inserted


def _migrate_from_lawson(dst: sqlite3.Connection) -> dict[str, int]:
    """Copy rows from lawson_freight.db (identical v2.1 schema)."""
    counts: dict[str, int] = {}
    src = _legacy_conn(LAWSON_DB)
    if src is None:
        return counts

    try:
        lead_map: dict[int, int] = {}
        if _table_exists(src, "leads"):
            for row in src.execute("SELECT * FROM leads ORDER BY id").fetchall():
                existing = dst.execute(
                    "SELECT id, phone, last_contact FROM leads WHERE company = ?",
                    (row["company"],),
                ).fetchone()
                if existing:
                    lead_map[int(row["id"])] = int(existing["id"])
                    updates: list[str] = []
                    values: list[Any] = []
                    if row["phone"] and row["phone"] != existing["phone"]:
                        updates.append("phone = ?")
                        values.append(row["phone"])
                    if row["last_contact"] and row["last_contact"] != existing["last_contact"]:
                        updates.append("last_contact = ?")
                        values.append(row["last_contact"])
                    if updates:
                        values.append(existing["id"])
                        dst.execute(
                            f"UPDATE leads SET {', '.join(updates)} WHERE id = ?",
                            values,
                        )
                else:
                    cur = dst.execute(
                        """
                        INSERT INTO leads (
                            company, contact_name, phone, email, commodity_focus,
                            lane_notes, status, priority, last_contact, created_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            row["company"],
                            row["contact_name"],
                            row["phone"],
                            row["email"],
                            row["commodity_focus"],
                            row["lane_notes"],
                            row["status"],
                            row["priority"],
                            row["last_contact"],
                            row["created_at"],
                        ),
                    )
                    lead_map[int(row["id"])] = int(cur.lastrowid)
            counts["leads"] = len(lead_map)

        if _table_exists(src, "loads"):
            load_count = 0
            for row in src.execute("SELECT * FROM loads ORDER BY id").fetchall():
                bol = _normalize_bol(row["bol_number"], row["id"])
                if dst.execute(
                    "SELECT 1 FROM loads WHERE bol_number = ?",
                    (bol,),
                ).fetchone():
                    continue
                mapped_lead = lead_map.get(int(row["lead_id"])) if row["lead_id"] else None
                dst.execute(
                    """
                    INSERT INTO loads (
                        bol_number, shipper, commodity, weight_tons, miles,
                        loaded_miles, deadhead_miles, pickup_date, delivery_date, origin,
                        destination, rate_per_ton, total_revenue, status, notes, lead_id, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        bol,
                        row["shipper"],
                        row["commodity"],
                        row["weight_tons"],
                        row["miles"],
                        row["loaded_miles"],
                        row["deadhead_miles"],
                        row["pickup_date"],
                        row["delivery_date"],
                        row["origin"],
                        row["destination"],
                        row["rate_per_ton"],
                        row["total_revenue"],
                        row["status"],
                        row["notes"],
                        mapped_lead,
                        row["created_at"],
                    ),
                )
                load_count += 1
            counts["loads"] = load_count

        for table in (
            "call_logs",
            "compliance",
            "telematics",
            "fuel",
            "maintenance",
            "ai_suggestions",
            "geofences",
            "geofence_events",
            "sms_log",
        ):
            dedupe_sql = None
            dedupe_args_fn = None
            if table == "geofences":
                dedupe_sql = "SELECT 1 FROM geofences WHERE name = ?"
                dedupe_args_fn = lambda p: (p.get("name"),)
            elif table == "compliance":
                dedupe_sql = "SELECT 1 FROM compliance WHERE item = ?"
                dedupe_args_fn = lambda p: (p.get("item"),)
            elif table == "ai_suggestions":
                dedupe_sql = "SELECT 1 FROM ai_suggestions WHERE title = ? AND category = ?"
                dedupe_args_fn = lambda p: (p.get("title"), p.get("category"))

            counts[table] = _copy_simple_table(
                src,
                dst,
                table,
                dedupe_sql=dedupe_sql,
                dedupe_args_fn=dedupe_args_fn,
            )

        if _table_exists(src, "app_settings"):
            for row in src.execute(
                "SELECT key, value, updated_at FROM app_settings"
            ).fetchall():
                dst.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (?,?,?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (row["key"], row["value"], row["updated_at"]),
                )
            counts["app_settings"] = dst.execute(
                "SELECT changes()"
            ).fetchone()[0]
    finally:
        src.close()

    return counts


def _migrate_from_lp_freight(dst: sqlite3.Connection) -> dict[str, int]:
    """Map older lp_freight.db schema into lp_dispatch.db."""
    counts: dict[str, int] = {}
    src = _legacy_conn(LP_FREIGHT_DB)
    if src is None:
        return counts

    try:
        lead_map: dict[int, int] = {}
        if _table_exists(src, "leads"):
            for row in src.execute("SELECT * FROM leads ORDER BY id").fetchall():
                lane_notes = row["lane_focus"]
                if row["notes"]:
                    lane_notes = f"{lane_notes} · {row['notes']}" if lane_notes else row["notes"]
                existing = dst.execute(
                    "SELECT id FROM leads WHERE company = ?",
                    (row["company"],),
                ).fetchone()
                if existing:
                    lead_map[int(row["id"])] = int(existing["id"])
                    if row["last_contacted"]:
                        dst.execute(
                            "UPDATE leads SET last_contact = ? WHERE id = ?",
                            (row["last_contacted"], existing["id"]),
                        )
                else:
                    cur = dst.execute(
                        """
                        INSERT INTO leads (
                            company, contact_name, phone, commodity_focus,
                            lane_notes, status, priority, last_contact, created_at
                        ) VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            row["company"],
                            row["contact"],
                            row["phone"],
                            row["commodity_fit"],
                            lane_notes,
                            row["status"],
                            row["priority"],
                            row["last_contacted"],
                            row["created_at"],
                        ),
                    )
                    lead_map[int(row["id"])] = int(cur.lastrowid)
            counts["leads"] = len(lead_map)

        if _table_exists(src, "loads"):
            load_count = 0
            for row in src.execute("SELECT * FROM loads ORDER BY id").fetchall():
                bol = _normalize_bol(row["bol_number"], row["id"])
                if dst.execute(
                    "SELECT 1 FROM loads WHERE bol_number = ?",
                    (bol,),
                ).fetchone():
                    continue
                miles = (row["loaded_miles"] or 0) + (row["deadhead_miles"] or 0)
                if miles <= 0:
                    miles = row["loaded_miles"] or row["deadhead_miles"] or PRIMARY_LANE["loaded_miles"]
                mapped_lead = _lead_id_by_company(dst, row["shipper"]) if row["shipper"] else None
                dst.execute(
                    """
                    INSERT INTO loads (
                        bol_number, shipper, commodity, weight_tons, miles,
                        loaded_miles, deadhead_miles, pickup_date, origin, destination,
                        rate_per_ton, total_revenue, status, notes, lead_id, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        bol,
                        row["shipper"],
                        row["commodity"],
                        row["tons"],
                        miles,
                        row["loaded_miles"],
                        row["deadhead_miles"],
                        row["load_date"],
                        row["origin"],
                        row["destination"],
                        row["rate_per_ton"],
                        row["total_revenue"],
                        row["load_status"] or "Imported",
                        row["notes"],
                        mapped_lead,
                        row["created_at"],
                    ),
                )
                load_count += 1
            counts["loads"] = load_count

        if _table_exists(src, "compliance_items"):
            comp_count = 0
            for row in src.execute("SELECT * FROM compliance_items ORDER BY id").fetchall():
                if dst.execute(
                    "SELECT 1 FROM compliance WHERE item = ?",
                    (row["item"],),
                ).fetchone():
                    continue
                dst.execute(
                    """
                    INSERT INTO compliance (item, status, due_date, notes, updated_at)
                    VALUES (?,?,?,?,?)
                    """,
                    (
                        row["item"],
                        row["status"],
                        row["due_date"],
                        row["notes"],
                        row["last_updated"],
                    ),
                )
                comp_count += 1
            counts["compliance"] = comp_count

        if _table_exists(src, "fuel_transactions"):
            fuel_count = 0
            for row in src.execute("SELECT * FROM fuel_transactions ORDER BY id").fetchall():
                dst.execute(
                    """
                    INSERT INTO fuel (
                        fill_date, gallons, cost, odometer, state, vendor, notes, imported_at
                    ) VALUES (?,?,?,?,?,?,?, datetime('now'))
                    """,
                    (
                        row["transaction_date"],
                        row["gallons"],
                        row["total_cost"],
                        row["odometer"],
                        row["location"],
                        row["vehicle"] if "vehicle" in row.keys() else None,
                        row["notes"],
                    ),
                )
                fuel_count += 1
            counts["fuel"] = fuel_count

        if _table_exists(src, "telematics_logs"):
            tele_count = 0
            for row in src.execute("SELECT * FROM telematics_logs ORDER BY id").fetchall():
                dst.execute(
                    """
                    INSERT INTO telematics (
                        recorded_at, odometer, engine_hours, latitude,
                        longitude, speed_mph, fuel_level_pct, notes, imported_at
                    ) VALUES (?,?,?,?,?,?,?,?, datetime('now'))
                    """,
                    (
                        row["log_date"],
                        row["parsed_odometer"],
                        row["parsed_hours"],
                        None,
                        None,
                        None,
                        row["parsed_fuel"],
                        row["parsed_location"],
                    ),
                )
                tele_count += 1
            counts["telematics"] = tele_count

        if _table_exists(src, "maintenance_logs"):
            maint_count = 0
            for row in src.execute("SELECT * FROM maintenance_logs ORDER BY id").fetchall():
                dst.execute(
                    """
                    INSERT INTO maintenance (
                        asset, task, status, due_date, completed_date,
                        odometer, cost, notes, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        row["asset_name"],
                        row["category"],
                        row["status"] or "Completed",
                        row["due_date"],
                        row["service_date"],
                        row["odometer"],
                        row["cost"],
                        row["notes"],
                        row["created_at"],
                    ),
                )
                maint_count += 1
            counts["maintenance"] = maint_count

        if _table_exists(src, "call_logs"):
            call_count = 0
            for row in src.execute(
                """
                SELECT c.*, l.company
                FROM call_logs c
                LEFT JOIN leads l ON c.lead_id = l.id
                ORDER BY c.id
                """
            ).fetchall():
                mapped_lead = lead_map.get(int(row["lead_id"])) if row["lead_id"] else None
                dst.execute(
                    """
                    INSERT INTO call_logs (lead_id, call_type, notes, outcome, logged_at)
                    VALUES (?,?,?,?,?)
                    """,
                    (
                        mapped_lead,
                        "Legacy",
                        row["notes"],
                        row["outcome"],
                        row["call_date"],
                    ),
                )
                call_count += 1
            counts["call_logs"] = call_count
    finally:
        src.close()

    return counts


def migrate_legacy_databases(force: bool = False) -> dict[str, Any]:
    """
    One-time import from lawson_freight.db and lp_freight.db into lp_dispatch.db.
    Stores a JSON report in app_settings for the Settings tab.
    """
    if not force and get_setting(MIGRATION_SETTING_KEY) == "completed":
        cached = get_setting(MIGRATION_REPORT_KEY)
        if cached:
            try:
                report = json.loads(cached)
                report["message"] = "Migration already completed."
                return report
            except json.JSONDecodeError:
                pass
        return {"status": "completed", "message": "Migration already completed."}

    with closing(get_conn()) as conn:
        lawson_counts = _migrate_from_lawson(conn)
        lp_counts = _migrate_from_lp_freight(conn)
        conn.commit()

    total_imported = sum(lawson_counts.values()) + sum(lp_counts.values())
    if total_imported > 0:
        message = (
            f"L & P Dispatch imported {total_imported} legacy row(s) "
            "from lawson_freight.db and lp_freight.db."
        )
        status = "completed"
    else:
        message = "Legacy databases checked — no new rows needed importing."
        status = "completed"

    report: dict[str, Any] = {
        "status": status,
        "migrated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": {
            "lawson_freight.db": {
                "path": str(LAWSON_DB),
                "found": LAWSON_DB.exists(),
                "counts": lawson_counts,
            },
            "lp_freight.db": {
                "path": str(LP_FREIGHT_DB),
                "found": LP_FREIGHT_DB.exists(),
                "counts": lp_counts,
            },
        },
        "total_rows_imported": total_imported,
        "message": message,
    }

    set_setting(MIGRATION_SETTING_KEY, "completed")
    set_setting(MIGRATION_REPORT_KEY, json.dumps(report))
    set_setting(MIGRATION_BANNER_KEY, "1" if total_imported > 0 else "0")
    clear_cache()
    return report


def init_db() -> None:
    """Create schema, seed baseline data, ensure opportunities, and migrate legacy DBs."""
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    with closing(get_conn()) as conn:
        conn.executescript(_SCHEMA_SQL)
        ensure_opportunities_table(conn)

        load_cols = {row[1] for row in conn.execute("PRAGMA table_info(loads)").fetchall()}
        if "voice_audio_path" not in load_cols:
            conn.execute("ALTER TABLE loads ADD COLUMN voice_audio_path TEXT")
        if "accepted_at" not in load_cols:
            conn.execute("ALTER TABLE loads ADD COLUMN accepted_at TEXT")
        if "bol_photo_path" not in load_cols:
            conn.execute("ALTER TABLE loads ADD COLUMN bol_photo_path TEXT")

        lead_cols = {row[1] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}
        for col in ("next_followup_date", "followup_type", "notes"):
            if col not in lead_cols:
                conn.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT")

        if conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 0:
            for lead in SEED_LEADS:
                conn.execute(
                    """
                    INSERT INTO leads (
                        company, contact_name, phone, commodity_focus,
                        lane_notes, status, priority
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        lead["company"],
                        lead["contact_name"],
                        lead["phone"],
                        lead["commodity_focus"],
                        lead["lane_notes"],
                        lead["status"],
                        lead["priority"],
                    ),
                )

        if conn.execute("SELECT COUNT(*) FROM compliance").fetchone()[0] == 0:
            for item, status, due_date, notes in SEED_COMPLIANCE:
                conn.execute(
                    "INSERT INTO compliance (item, status, due_date, notes) VALUES (?,?,?,?)",
                    (item, status, due_date, notes),
                )

        if conn.execute("SELECT COUNT(*) FROM geofences").fetchone()[0] == 0:
            for geo in SEED_GEOFENCES:
                conn.execute(
                    """
                    INSERT INTO geofences (
                        name, location_label, geofence_type,
                        latitude, longitude, radius_m, notes
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        geo["name"],
                        geo["location_label"],
                        geo["geofence_type"],
                        geo["latitude"],
                        geo["longitude"],
                        geo["radius_m"],
                        geo["notes"],
                    ),
                )

        load_cols = {row[1] for row in conn.execute("PRAGMA table_info(loads)").fetchall()}
        if "asset_id" not in load_cols:
            conn.execute("ALTER TABLE loads ADD COLUMN asset_id INTEGER")
        if "route_id" not in load_cols:
            conn.execute("ALTER TABLE loads ADD COLUMN route_id INTEGER")

        conn.commit()

    migrate_legacy_databases()
    _migrate_legacy_phase1_db()
    clear_cache()


_ASSETS_SEED = [
    ("Truck+Trailer", "Tractor + 39ft End-Dump", "Primary unit", 1.75, 0.85),
    ("Truck+Trailer", "Backup Tractor + Trailer", "Secondary unit", 1.65, 0.80),
    ("Trailer", "39ft End-Dump Only", "Trailer only", 1.50, 0.75),
]

_CUSTOMERS_SEED = [
    ("Kohler Co.", "Dispatch", "706-555-0100", "dispatch@kohler.example", None, "Primary GA receiver"),
    ("Sibelco Spruce Pine", "Sales", "828-555-0200", "sales@sibelco.example", None, "Primary NC shipper"),
    ("Covia", "Logistics", "1-800-555-0300", "logistics@covia.example", None, "National miner"),
]


def seed_assets() -> None:
    with closing(get_conn()) as conn:
        if conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0:
            for a in _ASSETS_SEED:
                conn.execute(
                    "INSERT INTO assets (asset_type, name, description, loaded_rate_per_mile, empty_rate_per_mile) VALUES (?,?,?,?,?)",
                    a,
                )
            conn.commit()


def seed_customers() -> None:
    with closing(get_conn()) as conn:
        if conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
            for c in _CUSTOMERS_SEED:
                conn.execute(
                    "INSERT INTO customers (name, contact_name, phone, email, api_key, notes) VALUES (?,?,?,?,?,?)",
                    c,
                )
            conn.commit()


def _migrate_legacy_phase1_db() -> None:
    """One-time copy from l_and_p_freight.db into lp_dispatch.db if present."""
    legacy = BASE_DIR / "l_and_p_freight.db"
    if not legacy.exists():
        return
    try:
        src = sqlite3.connect(legacy)
        dst = get_conn()
        for table in ("assets", "settlements", "routes", "customers", "purchase_orders", "po_loads", "eld_events"):
            try:
                _copy_simple_table(src, dst, table)
            except Exception:
                pass
        dst.commit()
        src.close()
    except Exception:
        pass


@st.cache_data(show_spinner=False)
def fetch_leads() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            "SELECT * FROM leads ORDER BY priority, company",
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_loads() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            "SELECT * FROM loads ORDER BY pickup_date DESC, id DESC",
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_call_logs() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            """
            SELECT c.*, l.company
            FROM call_logs c
            LEFT JOIN leads l ON c.lead_id = l.id
            ORDER BY c.logged_at DESC
            LIMIT 100
            """,
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_compliance() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            "SELECT * FROM compliance ORDER BY due_date",
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_telematics() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            "SELECT * FROM telematics ORDER BY recorded_at DESC LIMIT 500",
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_fuel() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            "SELECT * FROM fuel ORDER BY fill_date DESC LIMIT 500",
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_maintenance() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            "SELECT * FROM maintenance ORDER BY due_date",
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_geofences() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            "SELECT * FROM geofences WHERE active = 1 ORDER BY name",
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_geofence_events() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            "SELECT * FROM geofence_events ORDER BY logged_at DESC LIMIT 50",
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_sms_log() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            """
            SELECT s.*, l.company
            FROM sms_log s
            LEFT JOIN leads l ON s.lead_id = l.id
            ORDER BY s.logged_at DESC
            LIMIT 50
            """,
            conn,
        )


@st.cache_data(show_spinner=False)
def fetch_ai_suggestions() -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(
            "SELECT * FROM ai_suggestions WHERE dismissed = 0 ORDER BY id DESC",
            conn,
        )


def nuclear_delete_all_data() -> None:
    """Permanently delete lp_dispatch.db and all attachment files, then re-init."""
    clear_cache()
    if DB_PATH.exists():
        DB_PATH.unlink()
    if ATTACHMENTS_DIR.exists():
        shutil.rmtree(ATTACHMENTS_DIR)
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    clear_cache()


def seed_demo_data(force: bool = False) -> dict[str, Any]:
    """
    Seed impressive demo loads, fuel, maintenance, geofence events, and a call log.
    Sets demo_mode_active=1 when complete.
    """
    with closing(get_conn()) as conn:
        existing = int(conn.execute("SELECT COUNT(*) FROM loads").fetchone()[0])
        if existing > 0 and not force:
            return {
                "skipped": True,
                "message": "Data exists — enable force to re-seed.",
            }

        for table in ("loads", "fuel", "telematics", "geofence_events", "call_logs", "maintenance"):
            if table in _ALLOWED_TABLES:
                conn.execute(f'DELETE FROM "{table}"')

        origin = PRIMARY_LANE["origin"]
        destination = PRIMARY_LANE["destination"]
        load_count = 0

        for shipper, commodity, weight, miles, loaded_miles, days_ago in _DEMO_LOADS:
            rate, revenue = calculate_rate(weight, miles, loaded_miles, commodity)
            deadhead = max(0.0, float(miles) - float(loaded_miles))
            pickup = (date.today() - timedelta(days=days_ago)).isoformat()
            conn.execute(
                """
                INSERT INTO loads (
                    bol_number, shipper, commodity, weight_tons, miles,
                    loaded_miles, deadhead_miles, pickup_date, origin, destination,
                    rate_per_ton, total_revenue, status, notes
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    generate_bol_number(),
                    shipper,
                    commodity,
                    weight,
                    miles,
                    loaded_miles,
                    deadhead,
                    pickup,
                    origin,
                    destination,
                    rate,
                    revenue,
                    "Completed",
                    "Demo mode — L & P Dispatch Freight OS showcase load.",
                ),
            )
            load_count += 1

        for days_ago, gallons, cost, odometer, state in _DEMO_FUEL:
            fill_date = (date.today() - timedelta(days=days_ago)).isoformat()
            conn.execute(
                """
                INSERT INTO fuel (fill_date, gallons, cost, odometer, state, vendor, notes)
                VALUES (?,?,?,?,?,?,?)
                """,
                (fill_date, gallons, cost, odometer, state, "Pilot", "Demo fuel entry"),
            )

        conn.execute(
            """
            INSERT INTO maintenance (asset, task, status, due_date, cost, notes)
            VALUES (?,?,?,?,?,?)
            """,
            (
                "39ft End-Dump Trailer",
                "Liner inspection",
                "Scheduled",
                (date.today() + timedelta(days=18)).isoformat(),
                450.0,
                "Demo — predictive alert",
            ),
        )
        conn.execute(
            """
            INSERT INTO maintenance (asset, task, status, due_date, cost, notes)
            VALUES (?,?,?,?,?,?)
            """,
            (
                "Tractor",
                "Oil & filter service",
                "Scheduled",
                (date.today() + timedelta(days=9)).isoformat(),
                280.0,
                "Demo — before next Kohler run",
            ),
        )

        conn.execute(
            """
            INSERT INTO geofence_events (geofence_name, distance_m, latitude, longitude)
            VALUES (?,?,?,?)
            """,
            ("Kohler Central GA", 120.0, 32.98, -82.72),
        )

        sibelco = conn.execute(
            "SELECT id FROM leads WHERE company='Sibelco'"
        ).fetchone()
        if sibelco:
            conn.execute(
                """
                INSERT INTO call_logs (lead_id, call_type, notes, outcome)
                VALUES (?,?,?,?)
                """,
                (
                    sibelco["id"],
                    "Outbound",
                    "Demo: rate $48/ton feldspar confirmed",
                    "Spoke — load offered",
                ),
            )

        conn.commit()

    set_setting(DEMO_MODE_KEY, "1")
    clear_cache()
    return {
        "skipped": False,
        "loads": load_count,
        "message": "Demo data seeded — ready to impress.",
    }