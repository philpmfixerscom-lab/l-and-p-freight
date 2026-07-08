"""Customer Portal helpers for L & P Freight."""

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


def init_customer_portal() -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_name TEXT,
            phone TEXT,
            email TEXT,
            api_key TEXT UNIQUE,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            po_number TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'Open',
            total_estimated_revenue REAL DEFAULT 0.0,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    c.execute("""
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
        )
    """)
    conn.commit()
    conn.close()


def seed_demo_customers() -> None:
    conn = get_conn()
    c = conn.cursor()
    existing = c.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    if existing == 0:
        customers = [
            ("Kohler Co.", "Dispatch", "706-555-0100", "dispatch@kohler.example", None, "Primary GA receiver"),
            ("Sibelco Spruce Pine", "Sales", "828-555-0200", "sales@sibelco.example", None, "Primary NC shipper"),
            ("Covia", "Logistics", "1-800-555-0300", "logistics@covia.example", None, "National miner"),
        ]
        for cust in customers:
            c.execute("INSERT INTO customers (name, contact_name, phone, email, api_key, notes) VALUES (?,?,?,?,?,?)", cust)
        conn.commit()
    conn.close()


def fetch_customers() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM customers ORDER BY name", conn)
    conn.close()
    return df


def fetch_purchase_orders(customer_id: int | None = None) -> pd.DataFrame:
    conn = get_conn()
    q = "SELECT po.*, c.name as customer_name FROM purchase_orders po LEFT JOIN customers c ON po.customer_id = c.id"
    params: tuple[Any, ...] = ()
    if customer_id is not None:
        q += " WHERE po.customer_id = ?"
        params = (customer_id,)
    q += " ORDER BY po.created_at DESC"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def fetch_po_loads(po_id: int | None = None) -> pd.DataFrame:
    conn = get_conn()
    q = """
        SELECT pl.*, l.bol_number, l.shipper, l.commodity, l.total_revenue, l.status as load_status
        FROM po_loads pl
        LEFT JOIN loads l ON pl.load_id = l.id
    """
    params: tuple[Any, ...] = ()
    if po_id is not None:
        q += " WHERE pl.po_id = ?"
        params = (po_id,)
    q += " ORDER BY pl.sequence, pl.id"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def create_purchase_order(customer_id: int, po_number: str, status: str = "Open", notes: str = "") -> int:
    conn = get_conn()
    conn.execute(
        "INSERT INTO purchase_orders (customer_id, po_number, status, notes) VALUES (?,?,?,?)",
        (customer_id, po_number, status, notes),
    )
    conn.commit()
    po_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.close()
    return po_id


def add_po_load(
    po_id: int,
    load_id: int | None = None,
    sequence: int = 1,
    pickup_date: Any = None,
    delivery_date: Any = None,
    status: str = "Scheduled",
    notes: str = "",
) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO po_loads (po_id, load_id, sequence, scheduled_pickup_date, scheduled_delivery_date, status, notes)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            po_id,
            load_id,
            sequence,
            str(pickup_date) if pickup_date else None,
            str(delivery_date) if delivery_date else None,
            status,
            notes,
        ),
    )
    conn.commit()
    conn.close()


def update_po_status(po_id: int, status: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE purchase_orders SET status = ? WHERE id = ?", (status, po_id))
    conn.commit()
    conn.close()


def update_po_load_status(po_load_id: int, status: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE po_loads SET status = ? WHERE id = ?", (status, po_load_id))
    conn.commit()
    conn.close()


def get_customer_po_summary(customer_id: int) -> dict[str, Any]:
    po_df = fetch_purchase_orders(customer_id=customer_id)
    if po_df.empty:
        return {"open_pos": 0, "scheduled_loads": 0, "total_est_revenue": 0.0}
    open_pos = int((po_df["status"] == "Open").sum())
    po_ids = po_df["id"].tolist()
    conn = get_conn()
    placeholders = ",".join("?" for _ in po_ids)
    scheduled_df = pd.read_sql(
        f"SELECT COUNT(*) as cnt FROM po_loads WHERE po_id IN ({placeholders}) AND status = 'Scheduled'",
        conn,
        params=po_ids,
    )
    total_est = float(po_df["total_estimated_revenue"].fillna(0).sum())
    conn.close()
    return {
        "open_pos": open_pos,
        "scheduled_loads": int(scheduled_df.iloc[0]["cnt"]),
        "total_est_revenue": total_est,
    }
