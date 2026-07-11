"""Tests for billing: invoice PDF, auto-invoice on accept, QuickPay flag."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import lp_helpers.database as dbmod
from lp_helpers.billing import generate_invoice_pdf, queue_invoice, mark_invoice_sent, mark_quickpay, fetch_load
from lp_helpers.driver import accept_load


def _init(tmp_path: Path):
    db = tmp_path / "test_billing.db"
    old = dbmod.DB_PATH
    dbmod.DB_PATH = db
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE loads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bol_number TEXT, shipper TEXT, commodity TEXT,
            origin TEXT, destination TEXT, weight_tons REAL, rate_per_ton REAL,
            loaded_miles REAL, deadhead_miles REAL, total_revenue REAL, status TEXT, accepted_at TEXT
        );
        CREATE TABLE invoices (id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER, status TEXT DEFAULT 'Draft', created_at TEXT DEFAULT (datetime('now')), sent_at TEXT);
        CREATE TABLE settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER, total_pay REAL, quickpay INTEGER DEFAULT 0, status TEXT);
        CREATE TABLE po_loads (id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER, status TEXT);
        """
    )
    conn.execute(
        "INSERT INTO loads (id, bol_number, shipper, commodity, origin, destination, weight_tons, rate_per_ton, loaded_miles, deadhead_miles, total_revenue, status) "
        "VALUES (1,'LP-A','Sibelco','Feldspar','Spruce Pine, NC','GA',22,55,300,60,5000,'Logged')"
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


class TestBilling:
    def test_invoice_pdf_bytes(self, db):
        load = fetch_load(1)
        data = generate_invoice_pdf(load)
        assert data[:4] == b"%PDF"

    def test_queue_invoice_draft(self, db):
        queue_invoice(1)
        conn = dbmod.get_conn()
        row = conn.execute("SELECT status FROM invoices WHERE load_id=1").fetchone()
        conn.close()
        assert row["status"] == "Draft"

    def test_accept_auto_invoices(self, db):
        accept_load(1)
        conn = dbmod.get_conn()
        inv = conn.execute("SELECT status FROM invoices WHERE load_id=1").fetchone()
        conn.close()
        assert inv is not None and inv["status"] == "Draft"

    def test_mark_sent_and_quickpay(self, db):
        conn = dbmod.get_conn()
        conn.execute("INSERT INTO settlements (load_id, total_pay, quickpay, status) VALUES (1, 5000, 0, 'Draft')")
        sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        mark_quickpay(sid)
        conn = dbmod.get_conn()
        qp = conn.execute("SELECT quickpay FROM settlements WHERE id=?", (sid,)).fetchone()["quickpay"]
        conn.close()
        assert qp == 1
        mark_invoice_sent(99)  # no-op safe
