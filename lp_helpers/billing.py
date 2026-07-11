"""Billing helpers: customer invoice PDF, auto-invoicing on accept, QuickPay."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fpdf import FPDF

from lp_helpers.database import DB_PATH, get_conn


def _ascii(text) -> str:
    """fpdf core fonts are latin-1 only; normalize common unicode dashes."""
    return (
        str(text)
        .replace("—", "-")
        .replace("–", "-")
        .replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def generate_invoice_pdf(load: dict[str, Any]) -> bytes:
    """Render a customer invoice PDF for a load (now the single source of truth)."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _ascii("L & P Freight - Invoice"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
    pdf.ln(4)
    total_miles = (load.get("loaded_miles", 0) or 0) + (load.get("deadhead_miles", 0) or 0)
    rows = [
        ("To", str(load.get("shipper", "-"))),
        ("BOL #", str(load.get("bol_number", "-"))),
        ("Origin", str(load.get("origin") or "Spruce Pine, NC")),
        ("Destination", str(load.get("destination") or "Central Georgia (Kohler)")),
        ("Commodity", str(load.get("commodity", "-"))),
        ("Weight", f"{load.get('weight_tons', 0)} tons"),
        ("Miles", f"{total_miles:.0f} mi"),
        ("Rate/Ton", f"${float(load.get('rate_per_ton', 0) or 0):.2f}"),
        ("Total", f"${float(load.get('total_revenue', 0) or 0):.2f}"),
    ]
    for label, value in rows:
        pdf.cell(45, 7, _ascii(label), border=1)
        pdf.cell(0, 7, _ascii(value), border=1, ln=True)
    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)


def fetch_load(load_id: int, conn=None) -> dict[str, Any] | None:
    own = conn is None
    if own:
        conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM loads WHERE id = ?", (load_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        if own:
            conn.close()


def queue_invoice(load_id: int) -> None:
    """Create a Draft customer invoice the moment a load is accepted."""
    conn = get_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS invoices ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, load_id INTEGER, status TEXT DEFAULT 'Draft', "
            "created_at TEXT DEFAULT (datetime('now')), sent_at TEXT)"
        )
        exists = conn.execute(
            "SELECT 1 FROM invoices WHERE load_id = ? AND status = 'Draft'", (load_id,)
        ).fetchone()
        if not exists:
            conn.execute("INSERT INTO invoices (load_id, status) VALUES (?, 'Draft')", (load_id,))
        conn.commit()
    finally:
        conn.close()


def mark_invoice_sent(invoice_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE invoices SET status = 'Sent', sent_at = datetime('now') WHERE id = ?",
            (invoice_id,),
        )
        conn.commit()
    finally:
        conn.close()


def mark_quickpay(settlement_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE settlements SET quickpay = 1 WHERE id = ?", (settlement_id,))
        conn.commit()
    finally:
        conn.close()


def list_invoices(conn=None) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT i.id, i.load_id, i.status, i.created_at, l.bol_number, l.shipper, l.total_revenue "
            "FROM invoices i LEFT JOIN loads l ON i.load_id = l.id ORDER BY i.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()
