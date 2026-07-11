"""Notifications engine for L & P Freight.

Derives actionable alerts from existing data (new leads, load accepts, late
loads, deadhead watch, route-variance flags) and groups them Today / Yesterday /
Earlier. Dismissals persist so the center stays clean across reloads.
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any

from lp_helpers.database import get_conn
from lp_helpers.pay_engine import mileage_reconciliation

CATEGORY_META: dict[str, tuple[str, str]] = {
    "lead": ("New Lead", "blue"),
    "accepted": ("Load Accepted", "green"),
    "late": ("Late Load", "red"),
    "deadhead": ("Deadhead Watch", "amber"),
    "variance": ("Route Variance", "amber"),
    "eld": ("ELD", "blue"),
}

ACTIVE_FOR_LATE = ("Accepted", "In Transit")
ACTIVE_FOR_DEADHEAD = ("Accepted", "In Transit", "Delivered")


def _parse_ts(ts: str | None) -> datetime:
    if not ts:
        return datetime.now()
    s = str(ts).replace(" ", "T")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.fromisoformat(s + "T00:00:00")


def derive_notifications(conn) -> list[dict[str, Any]]:
    """Build the list of current notifications from live data."""
    items: list[dict[str, Any]] = []
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    # New / recent hot leads
    for r in conn.execute("SELECT id, company, status, created_at FROM leads").fetchall():
        created = _parse_ts(r["created_at"])
        if created >= week_ago:
            items.append({
                "key": f"lead:{r['id']}",
                "category": "lead",
                "title": f"New lead: {r['company']}",
                "detail": f"Status: {r['status']}",
                "ts": r["created_at"],
                "screen": "Leads",
            })

    # Accepted loads -> customer billing live
    for r in conn.execute(
        "SELECT id, bol_number, shipper, accepted_at FROM loads WHERE accepted_at IS NOT NULL"
    ).fetchall():
        items.append({
            "key": f"accepted:{r['id']}",
            "category": "accepted",
            "title": f"Load {r['bol_number']} accepted",
            "detail": f"{r['shipper']} — billing is live for the customer",
            "ts": r["accepted_at"],
            "screen": "Billing & Pay",
        })

    # Loads that may be late (pickup date passed, not delivered)
    for r in conn.execute(
        "SELECT id, bol_number, shipper, pickup_date, status FROM loads "
        "WHERE status IN ('Accepted','In Transit')"
    ).fetchall():
        pd = _parse_ts(r["pickup_date"]).date() if r["pickup_date"] else None
        if pd and pd < now.date():
            items.append({
                "key": f"late:{r['id']}",
                "category": "late",
                "title": f"Load {r['bol_number']} may be late",
                "detail": f"{r['shipper']} — pickup was {r['pickup_date']}",
                "ts": r["pickup_date"],
                "screen": "Log Load",
            })

    # Deadhead watch (>= 35% empty miles on an active load)
    for r in conn.execute(
        "SELECT id, bol_number, deadhead_miles, loaded_miles, destination, accepted_at, pickup_date "
        "FROM loads WHERE status IN ('Accepted','In Transit','Delivered')"
    ).fetchall():
        dead = float(r["deadhead_miles"] or 0)
        loaded = float(r["loaded_miles"] or 0)
        total = dead + loaded
        if total > 0 and dead / total >= 0.35:
            pct = int(round(dead / total * 100))
            items.append({
                "key": f"deadhead:{r['id']}",
                "category": "deadhead",
                "title": f"Deadhead watch: {r['bol_number']}",
                "detail": f"{pct}% empty miles — find a backhaul from {r['destination']}",
                "ts": r["accepted_at"] or r["pickup_date"],
                "screen": "Maps",
            })

    # Route variance flags (actual vs Google/planned beyond tolerance)
    for r in conn.execute(
        "SELECT id, load_id, planned_loaded_miles, planned_empty_miles, "
        "actual_loaded_miles, actual_empty_miles, google_miles, updated_at "
        "FROM routes WHERE actual_loaded_miles IS NOT NULL"
    ).fetchall():
        recon = mileage_reconciliation(
            r["actual_loaded_miles"], r["actual_empty_miles"], r["google_miles"],
            r["planned_loaded_miles"], r["planned_empty_miles"],
        )
        if recon["flagged"]:
            items.append({
                "key": f"variance:{r['id']}",
                "category": "variance",
                "title": f"Route variance on load #{r['load_id']}",
                "detail": f"{recon['variance_pct']:+.1f}% vs {recon['basis_source']} — review pay",
                "ts": r["updated_at"],
                "screen": "Billing & Pay",
            })

    items.sort(key=lambda x: _parse_ts(x["ts"]), reverse=True)
    return items


def _ensure_schema(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notification_dismissals "
        "(key TEXT PRIMARY KEY, dismissed_at TEXT DEFAULT (datetime('now')))"
    )


def dismiss_notification(key: str) -> None:
    """Persist a dismissal so the alert stays cleared across reloads."""
    conn = get_conn()
    try:
        _ensure_schema(conn)
        conn.execute("INSERT OR IGNORE INTO notification_dismissals (key) VALUES (?)", (key,))
        conn.commit()
    finally:
        conn.close()


def get_notifications() -> dict[str, Any]:
    """Return grouped, non-dismissed notifications plus an unread count."""
    conn = get_conn()
    try:
        _ensure_schema(conn)
        dismissed = {row[0] for row in conn.execute("SELECT key FROM notification_dismissals").fetchall()}
        items = [i for i in derive_notifications(conn) if i["key"] not in dismissed]
    finally:
        conn.close()

    groups = {"Today": [], "Yesterday": [], "Earlier": []}
    today = date.today()
    for it in items:
        d = _parse_ts(it["ts"]).date()
        if d == today:
            groups["Today"].append(it)
        elif d == today - timedelta(days=1):
            groups["Yesterday"].append(it)
        else:
            groups["Earlier"].append(it)

    return {"groups": groups, "unread": len(items), "total": len(items)}


def group_notifications(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Pure grouping helper (used by tests and the UI)."""
    groups = {"Today": [], "Yesterday": [], "Earlier": []}
    today = date.today()
    for it in items:
        d = _parse_ts(it["ts"]).date()
        if d == today:
            groups["Today"].append(it)
        elif d == today - timedelta(days=1):
            groups["Yesterday"].append(it)
        else:
            groups["Earlier"].append(it)
    return groups
