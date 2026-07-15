"""Leads repository — always tenant-scoped."""

from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd

from lp_helpers.tenancy import DEFAULT_TENANT_ID, current_tenant_id


def list_leads(
    conn: sqlite3.Connection,
    tenant_id: str | None = None,
) -> pd.DataFrame:
    tid = tenant_id or current_tenant_id() or DEFAULT_TENANT_ID
    cols = {r[1] for r in conn.execute("PRAGMA table_info(leads)").fetchall()}
    if "tenant_id" in cols:
        df = pd.read_sql_query(
            """
            SELECT * FROM leads
            WHERE tenant_id = ? OR tenant_id IS NULL
            ORDER BY priority, company
            """,
            conn,
            params=(tid,),
        )
    else:
        df = pd.read_sql_query(
            "SELECT * FROM leads ORDER BY priority, company",
            conn,
        )
    if not df.empty:
        if "lane_notes" in df.columns:
            df["notes"] = df["lane_notes"].fillna("")
        elif "notes" not in df.columns:
            df["notes"] = ""
    return df


def insert_lead(
    conn: sqlite3.Connection,
    fields: dict[str, Any],
    *,
    tenant_id: str | None = None,
) -> int:
    tid = tenant_id or current_tenant_id() or DEFAULT_TENANT_ID
    cols = {r[1] for r in conn.execute("PRAGMA table_info(leads)").fetchall()}
    payload = dict(fields)
    if "tenant_id" in cols:
        payload.setdefault("tenant_id", tid)
    keys = list(payload.keys())
    cur = conn.execute(
        f"INSERT INTO leads ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
        tuple(payload[k] for k in keys),
    )
    return int(cur.lastrowid)
