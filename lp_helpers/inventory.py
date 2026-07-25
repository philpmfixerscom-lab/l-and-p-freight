"""Inventory & Replenishment Intelligence — Phase 1 helpers."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from lp_helpers.database import ATTACHMENTS_DIR, get_conn


INVENTORY_PHOTOS_DIR = ATTACHMENTS_DIR / "inventory_photos"
LEVEL_TONS_MAP = {
    "Empty": 0.0,
    "1/4": 0.25,
    "1/2": 0.5,
    "3/4": 0.75,
    "Full": 1.0,
}


def ensure_inventory_photos_dir() -> None:
    INVENTORY_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


def insert_inventory_estimate(
    conn: Any,
    *,
    lead_id: int | None,
    load_id: int | None,
    commodity: str,
    estimated_level: str,
    estimated_tons: float = 0.0,
    photo_paths: list[str] | None = None,
    driver_notes: str = "",
    estimated_by: str = "",
) -> int:
    """Insert a new inventory estimate and update lead last-estimate fields."""
    photo_paths_json = json.dumps(photo_paths or [])
    cur = conn.execute(
        """
        INSERT INTO inventory_estimates
            (lead_id, load_id, commodity, estimated_level, estimated_tons,
             photo_paths, driver_notes, estimated_by)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            lead_id,
            load_id,
            commodity,
            estimated_level,
            float(estimated_tons),
            photo_paths_json,
            driver_notes.strip(),
            estimated_by.strip(),
        ),
    )
    estimate_id = int(cur.lastrowid)

    if lead_id is not None:
        conn.execute(
            """
            UPDATE leads
            SET last_estimate_level = ?,
                last_estimate_date = ?
            WHERE id = ?
            """,
            (estimated_level, datetime.now().isoformat(), lead_id),
        )

    return estimate_id


def recalculate_days_of_supply(conn: Any, lead_id: int) -> float | None:
    """Recalculate days_of_supply_est for a lead.

    Formula: estimated_tons_remaining / avg_weekly_tons * 7
    Returns the new value, or None if avg_weekly_tons is missing/zero.
    """
    row = conn.execute(
        "SELECT avg_weekly_tons FROM leads WHERE id = ?",
        (lead_id,),
    ).fetchone()
    if row is None:
        return None
    avg_weekly_tons = float(row["avg_weekly_tons"] or 0)
    if avg_weekly_tons <= 0:
        return None

    est_row = conn.execute(
        """
        SELECT estimated_tons FROM inventory_estimates
        WHERE lead_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    if est_row is None:
        return None

    estimated_tons = float(est_row["estimated_tons"] or 0)
    days = (estimated_tons / avg_weekly_tons) * 7.0
    days = round(days, 1)

    conn.execute(
        "UPDATE leads SET days_of_supply_est = ? WHERE id = ?",
        (days, lead_id),
    )
    return days


def get_lead_inventory_latest(conn: Any, lead_id: int) -> dict[str, Any] | None:
    """Return the most recent inventory estimate for a lead as a dict."""
    row = conn.execute(
        """
        SELECT * FROM inventory_estimates
        WHERE lead_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    try:
        data["photo_paths"] = json.loads(data.get("photo_paths") or "[]")
    except (json.JSONDecodeError, TypeError):
        data["photo_paths"] = []
    return data


def save_inventory_photos(
    lead_id: int | None,
    load_id: int | None,
    files: list[Any],
) -> list[str]:
    """Persist uploaded inventory photos under attachments/inventory_photos/.

    Returns list of stored relative file paths.
    """
    ensure_inventory_photos_dir()
    saved: list[str] = []
    for f in files[:3]:
        if f is None:
            continue
        raw = f.getvalue() if hasattr(f, "getvalue") else f.read()
        name = getattr(f, "name", "photo.bin")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"inv_{lead_id or 0}_{stamp}_{name}".replace(" ", "_")
        dest = INVENTORY_PHOTOS_DIR / fname
        dest.write_bytes(raw)
        saved.append(str(dest))
    return saved


def days_of_supply_color(days: float | None) -> str:
    """Return a hex color based on days of supply remaining."""
    if days is None:
        return "#94a3b8"      # gray
    if days >= 14:
        return "#4ade80"      # green
    if days >= 7:
        return "#fbbf24"      # yellow
    return "#f87171"          # red


def render_days_of_supply(days: float | None) -> str:
    """Return an HTML span with color-coded days-of-supply text."""
    if days is None:
        return "—"
    color = days_of_supply_color(days)
    label = f"{days:.0f} days"
    return f"<span style='color:{color}; font-weight:600'>{label}</span>"


def level_to_tons(level: str, bin_capacity_tons: float = 24.0) -> float:
    """Convert a human-readable level label to estimated tons."""
    ratio = LEVEL_TONS_MAP.get(level, 0.0)
    return round(ratio * float(bin_capacity_tons), 2)
