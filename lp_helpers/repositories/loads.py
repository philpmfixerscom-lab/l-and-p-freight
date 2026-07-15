"""Load repository — always tenant-scoped."""

from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd

from lp_helpers.tenancy import DEFAULT_TENANT_ID, current_tenant_id


def list_loads(
    conn: sqlite3.Connection,
    tenant_id: str | None = None,
) -> pd.DataFrame:
    tid = tenant_id or current_tenant_id() or DEFAULT_TENANT_ID
    cols = {r[1] for r in conn.execute("PRAGMA table_info(loads)").fetchall()}
    if "tenant_id" in cols:
        return pd.read_sql_query(
            """
            SELECT *, pickup_date AS load_date
            FROM loads
            WHERE tenant_id = ? OR tenant_id IS NULL
            ORDER BY pickup_date DESC, id DESC
            """,
            conn,
            params=(tid,),
        )
    return pd.read_sql_query(
        """
        SELECT *, pickup_date AS load_date
        FROM loads
        ORDER BY pickup_date DESC, id DESC
        """,
        conn,
    )


def insert_load(
    conn: sqlite3.Connection,
    fields: dict[str, Any],
    *,
    tenant_id: str | None = None,
) -> int:
    """Insert a load row. Returns new id."""
    tid = tenant_id or current_tenant_id() or DEFAULT_TENANT_ID
    cols = {r[1] for r in conn.execute("PRAGMA table_info(loads)").fetchall()}
    payload = dict(fields)
    if "tenant_id" in cols:
        payload.setdefault("tenant_id", tid)

    keys = list(payload.keys())
    placeholders = ", ".join("?" for _ in keys)
    col_sql = ", ".join(keys)
    cur = conn.execute(
        f"INSERT INTO loads ({col_sql}) VALUES ({placeholders})",
        tuple(payload[k] for k in keys),
    )
    return int(cur.lastrowid)


def update_load_status(
    conn: sqlite3.Connection,
    load_id: int,
    status: str,
    *,
    notes_append: str = "",
    tenant_id: str | None = None,
) -> None:
    tid = tenant_id or current_tenant_id() or DEFAULT_TENANT_ID
    cols = {r[1] for r in conn.execute("PRAGMA table_info(loads)").fetchall()}
    if "tenant_id" in cols:
        if notes_append:
            conn.execute(
                """
                UPDATE loads SET status = ?,
                    notes = COALESCE(notes, '') || ?
                WHERE id = ? AND (tenant_id = ? OR tenant_id IS NULL)
                """,
                (status, notes_append, load_id, tid),
            )
        else:
            conn.execute(
                """
                UPDATE loads SET status = ?
                WHERE id = ? AND (tenant_id = ? OR tenant_id IS NULL)
                """,
                (status, load_id, tid),
            )
    else:
        if notes_append:
            conn.execute(
                "UPDATE loads SET status = ?, notes = COALESCE(notes, '') || ? WHERE id = ?",
                (status, notes_append, load_id),
            )
        else:
            conn.execute("UPDATE loads SET status = ? WHERE id = ?", (status, load_id))


def fetch_active_load_row(
    conn: sqlite3.Connection,
    tenant_id: str | None = None,
) -> dict[str, Any] | None:
    tid = tenant_id or current_tenant_id() or DEFAULT_TENANT_ID
    cols = {r[1] for r in conn.execute("PRAGMA table_info(loads)").fetchall()}
    if "tenant_id" in cols:
        row = conn.execute(
            """
            SELECT * FROM loads
            WHERE status IN ('Dispatched', 'In Transit', 'Booked', 'Arrived', 'Loaded')
              AND (tenant_id = ? OR tenant_id IS NULL)
            ORDER BY pickup_date DESC, id DESC
            LIMIT 1
            """,
            (tid,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT * FROM loads
            WHERE status IN ('Dispatched', 'In Transit', 'Booked', 'Arrived', 'Loaded')
            ORDER BY pickup_date DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}
