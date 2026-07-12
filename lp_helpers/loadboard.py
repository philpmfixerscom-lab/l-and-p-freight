"""Load Board: internal freight marketplace with search, filters, and one-tap assign."""

from __future__ import annotations

from typing import Any

from lp_helpers.database import get_conn


def fetch_board_loads(conn=None) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, bol_number, shipper, commodity, origin, destination, "
            "weight_tons, loaded_miles, deadhead_miles, total_revenue, rate_per_ton, status, pickup_date "
            "FROM loads ORDER BY pickup_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def filter_board(
    loads: list[dict[str, Any]],
    status: str | None = None,
    shipper: str | None = None,
    query: str = "",
) -> list[dict[str, Any]]:
    """Apply quick-filter chips + free-text search (BOL / shipper / commodity / lane)."""
    q = (query or "").strip().lower()
    out = loads
    if status and status != "All":
        out = [l for l in out if l.get("status") == status]
    if shipper and shipper != "All":
        out = [l for l in out if (l.get("shipper") or "") == shipper]
    if q:
        out = [
            l for l in out
            if q in str(l.get("bol_number", "")).lower()
            or q in str(l.get("shipper", "")).lower()
            or q in str(l.get("commodity", "")).lower()
            or q in str(l.get("origin", "")).lower()
            or q in str(l.get("destination", "")).lower()
        ]
    return out


def assign_load(load_id: int, to_customer: str | None = None) -> None:
    """One-tap assign: mark the load booked/accepted and flip customer billing live."""
    from lp_helpers.driver import accept_load

    accept_load(load_id, "Accepted")
    if to_customer:
        conn = get_conn()
        try:
            conn.execute("UPDATE loads SET notes = ? WHERE id = ?",
                         (f"Assigned to {to_customer}", load_id))
            conn.commit()
        finally:
            conn.close()


def board_status_options(loads: list[dict[str, Any]]) -> list[str]:
    opts = ["All"] + sorted({l.get("status") or "Unknown" for l in loads})
    return opts


def board_shipper_options(loads: list[dict[str, Any]]) -> list[str]:
    opts = ["All"] + sorted({l.get("shipper") or "Unknown" for l in loads})
    return opts
