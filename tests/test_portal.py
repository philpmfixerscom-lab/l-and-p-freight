"""Smoke tests for Customer Portal and PO functionality."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from portal import (
    init_customer_portal,
    seed_demo_customers,
    fetch_customers,
    fetch_purchase_orders,
    fetch_po_loads,
    create_purchase_order,
    add_po_load,
    update_po_status,
    update_po_load_status,
    get_customer_po_summary,
)


def _init_test_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_portal.db"
    import portal as mod
    old_db = mod.DB_PATH
    mod.DB_PATH = db
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            contact_name TEXT, phone TEXT, email TEXT, api_key TEXT UNIQUE,
            notes TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL,
            po_number TEXT UNIQUE NOT NULL, status TEXT DEFAULT 'Open',
            total_estimated_revenue REAL DEFAULT 0.0, notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS po_loads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, po_id INTEGER NOT NULL,
            load_id INTEGER, sequence INTEGER DEFAULT 1,
            scheduled_pickup_date TEXT, scheduled_delivery_date TEXT,
            status TEXT DEFAULT 'Scheduled', notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (po_id) REFERENCES purchase_orders(id),
            FOREIGN KEY (load_id) REFERENCES loads(id)
        );
        CREATE TABLE IF NOT EXISTS loads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bol_number TEXT,
            shipper TEXT, commodity TEXT, loaded_miles REAL,
            empty_miles REAL, total_revenue REAL, status TEXT
        );
        """
    )
    conn.execute("INSERT INTO loads (id, bol_number, shipper, commodity) VALUES (1, 'LP-TEST-1', 'Sibelco', 'Feldspar')")
    conn.commit()
    conn.close()
    try:
        yield db
    finally:
        mod.DB_PATH = old_db


@pytest.fixture()
def test_db(tmp_path: Path):
    yield from _init_test_db(tmp_path)


class TestCustomerPortal:
    def test_seed_customers(self, test_db):
        init_customer_portal()
        seed_demo_customers()
        df = fetch_customers()
        assert len(df) == 3
        assert "Kohler Co." in df["name"].values

    def test_create_po_and_add_loads(self, test_db):
        init_customer_portal()
        seed_demo_customers()
        custs = fetch_customers()
        cust_id = int(custs.iloc[0]["id"])
        po_id = create_purchase_order(cust_id, "PO-TEST-1", notes="Test PO")
        assert po_id > 0
        add_po_load(po_id, load_id=1, sequence=1, pickup_date="2026-07-06", delivery_date="2026-07-09")
        pol = fetch_po_loads(po_id=po_id)
        assert len(pol) == 1
        assert pol.iloc[0]["sequence"] == 1
        assert pol.iloc[0]["status"] == "Scheduled"

    def test_po_status_transitions(self, test_db):
        init_customer_portal()
        seed_demo_customers()
        custs = fetch_customers()
        cust_id = int(custs.iloc[0]["id"])
        po_id = create_purchase_order(cust_id, "PO-TRANS-1")
        update_po_status(po_id, "In Progress")
        pos = fetch_purchase_orders(customer_id=cust_id)
        row = pos[pos["id"] == po_id].iloc[0]
        assert row["status"] == "In Progress"
        update_po_status(po_id, "Complete")
        pos = fetch_purchase_orders(customer_id=cust_id)
        row = pos[pos["id"] == po_id].iloc[0]
        assert row["status"] == "Complete"

    def test_customer_summary(self, test_db):
        init_customer_portal()
        seed_demo_customers()
        custs = fetch_customers()
        cust_id = int(custs.iloc[0]["id"])
        create_purchase_order(cust_id, "PO-SUM-1", notes="Sum test")
        summary = get_customer_po_summary(cust_id)
        assert summary["open_pos"] >= 1
        assert summary["scheduled_loads"] == 0

    def test_billing_visibility_on_accept(self, test_db):
        init_customer_portal()
        seed_demo_customers()
        custs = fetch_customers()
        cust_id = int(custs.iloc[0]["id"])
        po_id = create_purchase_order(cust_id, "PO-BILL-1")
        add_po_load(po_id, load_id=1)
        pol = fetch_po_loads(po_id=po_id)
        load_row = pol.iloc[0]
        assert load_row["load_status"] == "Logged" or load_row["load_status"] is None
