"""Multi-tenant schema helpers (Phase B) — additive, non-breaking.

Default tenant: lp-freight. All business tables get nullable then backfilled
tenant_id so single-tenant deploys keep working with zero UX change.
"""

from __future__ import annotations

import sqlite3
from typing import Any

DEFAULT_TENANT_ID = "lp-freight"

# Tables that receive tenant_id in Phase B
TENANT_SCOPED_TABLES: tuple[str, ...] = (
    "leads",
    "loads",
    "call_logs",
    "sms_log",
    "opportunities",
    "geofences",
    "telematics",
    "fuel",
    "maintenance",
    "compliance",
    "ai_suggestions",
    "assets",
    "geofence_events",
)

_TENANTS_DDL = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE,
    status TEXT DEFAULT 'active',
    plan TEXT DEFAULT 'solo',
    settings_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    username TEXT,
    display_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    role TEXT DEFAULT 'owner_driver',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
"""

_VEHICLES_DDL = """
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    unit_number TEXT,
    label TEXT NOT NULL,
    vin TEXT,
    status TEXT DEFAULT 'Active',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
"""

_VEHICLE_PROVIDER_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS vehicle_provider_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    vehicle_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    provider_device_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE (tenant_id, provider, provider_device_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
);
"""

_API_CONNECTIONS_DDL = """
CREATE TABLE IF NOT EXISTS api_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    config_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE (tenant_id, provider),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
"""


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def ensure_multi_tenant_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    """Create tenancy tables, add tenant_id columns, backfill default tenant.

    Safe to call on every init_db(). Returns a small report for diagnostics.
    """
    report: dict[str, Any] = {"tenant_id": DEFAULT_TENANT_ID, "columns_added": [], "backfilled": {}}

    conn.executescript(
        _TENANTS_DDL
        + _USERS_DDL
        + _VEHICLES_DDL
        + _VEHICLE_PROVIDER_LINKS_DDL
        + _API_CONNECTIONS_DDL
    )

    # Seed default tenant
    conn.execute(
        """
        INSERT INTO tenants (id, name, slug, status, plan)
        VALUES (?, 'L & P Freight', 'lp-freight', 'active', 'solo')
        ON CONFLICT(id) DO UPDATE SET name = excluded.name
        """,
        (DEFAULT_TENANT_ID,),
    )

    for table in TENANT_SCOPED_TABLES:
        if not _table_exists(conn, table):
            continue
        cols = _table_columns(conn, table)
        if "tenant_id" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT")
            report["columns_added"].append(table)
            cols.add("tenant_id")

        # Backfill nulls
        cur = conn.execute(
            f"UPDATE {table} SET tenant_id = ? WHERE tenant_id IS NULL OR tenant_id = ''",
            (DEFAULT_TENANT_ID,),
        )
        report["backfilled"][table] = cur.rowcount

    # Index for common filters (ignore if exists)
    for table in ("leads", "loads", "opportunities"):
        if not _table_exists(conn, table):
            continue
        try:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant "
                f"ON {table}(tenant_id)"
            )
        except sqlite3.Error:
            pass

    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_loads_tenant_pickup "
            "ON loads(tenant_id, pickup_date DESC)"
        )
    except sqlite3.Error:
        pass

    return report


def current_tenant_id() -> str:
    """Resolve active tenant for this process/session (Phase B: default only)."""
    try:
        import streamlit as st

        tid = st.session_state.get("tenant_id")
        if tid:
            return str(tid)
    except Exception:
        pass
    try:
        from lp_helpers.fleet_context import get_tenant_context

        return get_tenant_context().tenant_id
    except Exception:
        return DEFAULT_TENANT_ID
