"""Inventory & Replenishment Intelligence — Phase 1 helpers."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from lp_helpers.database import ATTACHMENTS_DIR, get_conn


INVENTORY_PHOTOS_DIR = ATTACHMENTS_DIR / "inventory_photos"

# Driver-facing days-of-supply style labels (Phase 1 field form)
BIN_LEVEL_OPTIONS: tuple[str, ...] = (
    "Empty / Near Empty",
    "Low (1-2 days)",
    "Medium (3-7 days)",
    "High (1-2 weeks)",
    "Full / Overstocked",
)

# Fraction of bin capacity used when tons not entered (legacy + driver labels)
LEVEL_TONS_MAP = {
    # Legacy fraction labels (Dispatch / historical)
    "Empty": 0.0,
    "1/4": 0.25,
    "1/2": 0.5,
    "3/4": 0.75,
    "Full": 1.0,
    # Driver-facing supply labels
    "Empty / Near Empty": 0.0,
    "Low (1-2 days)": 0.15,
    "Medium (3-7 days)": 0.45,
    "High (1-2 weeks)": 0.75,
    "Full / Overstocked": 1.0,
}

# Canonical vs legacy column pairs (live DBs may have either or both)
_LEVEL_COLS = ("level", "estimated_level")
_TONS_COLS = ("tons_est", "estimated_tons")
_NOTES_COLS = ("notes", "driver_notes")


def ensure_inventory_photos_dir() -> None:
    INVENTORY_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


def inventory_estimate_columns(conn: Any) -> set[str]:
    """Return current column names on inventory_estimates."""
    return {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(inventory_estimates)").fetchall()
    }


def ensure_inventory_estimate_columns(conn: Any) -> set[str]:
    """Ensure dual-schema columns exist (legacy estimated_* + canonical level/tons_est).

    Older DBs created estimated_level NOT NULL; newer code uses level/tons_est.
    We keep both in sync so inserts never violate NOT NULL and reads stay consistent.
    """
    cols = inventory_estimate_columns(conn)
    for col, typedef in (
        ("lead_id", "INTEGER"),
        ("load_id", "INTEGER"),
        ("commodity", "TEXT"),
        ("estimate_date", "TEXT"),
        ("level", "TEXT"),
        ("tons_est", "REAL"),
        ("notes", "TEXT"),
        ("photo_paths", "TEXT"),
        ("estimated_by", "TEXT"),
        ("created_at", "TEXT"),
        ("estimated_level", "TEXT"),
        ("estimated_tons", "REAL"),
        ("driver_notes", "TEXT"),
    ):
        if col not in cols:
            try:
                conn.execute(
                    f"ALTER TABLE inventory_estimates ADD COLUMN {col} {typedef}"
                )
                cols.add(col)
            except Exception:
                pass
    # Backfill empty canonical columns from legacy (and vice-versa) for old rows
    try:
        if "level" in cols and "estimated_level" in cols:
            conn.execute(
                """
                UPDATE inventory_estimates
                SET level = estimated_level
                WHERE (level IS NULL OR level = '')
                  AND estimated_level IS NOT NULL AND estimated_level != ''
                """
            )
            conn.execute(
                """
                UPDATE inventory_estimates
                SET estimated_level = level
                WHERE (estimated_level IS NULL OR estimated_level = '')
                  AND level IS NOT NULL AND level != ''
                """
            )
        if "tons_est" in cols and "estimated_tons" in cols:
            conn.execute(
                """
                UPDATE inventory_estimates
                SET tons_est = estimated_tons
                WHERE tons_est IS NULL AND estimated_tons IS NOT NULL
                """
            )
            conn.execute(
                """
                UPDATE inventory_estimates
                SET estimated_tons = tons_est
                WHERE estimated_tons IS NULL AND tons_est IS NOT NULL
                """
            )
        if "notes" in cols and "driver_notes" in cols:
            conn.execute(
                """
                UPDATE inventory_estimates
                SET notes = driver_notes
                WHERE (notes IS NULL OR notes = '')
                  AND driver_notes IS NOT NULL AND driver_notes != ''
                """
            )
            conn.execute(
                """
                UPDATE inventory_estimates
                SET driver_notes = notes
                WHERE (driver_notes IS NULL OR driver_notes = '')
                  AND notes IS NOT NULL AND notes != ''
                """
            )
    except Exception:
        pass
    return cols


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
    """Insert a new inventory estimate and update lead last-estimate fields.

    Dual-writes level/estimated_level and tons_est/estimated_tons so both
    legacy production schemas and fresh schemas accept the row.
    """
    cols = ensure_inventory_estimate_columns(conn)
    photo_paths_json = json.dumps(photo_paths or [])
    stamp = datetime.now().isoformat(timespec="seconds")
    level_val = str(estimated_level or "").strip()
    tons_val = float(estimated_tons or 0.0)
    notes_val = str(driver_notes or "").strip()
    by_val = str(estimated_by or "").strip()

    payload: dict[str, Any] = {}
    if "lead_id" in cols:
        payload["lead_id"] = lead_id
    if "load_id" in cols:
        payload["load_id"] = load_id
    if "commodity" in cols:
        payload["commodity"] = commodity
    if "photo_paths" in cols:
        payload["photo_paths"] = photo_paths_json
    if "estimated_by" in cols:
        payload["estimated_by"] = by_val
    if "estimate_date" in cols:
        payload["estimate_date"] = stamp
    # Dual-write level / tons / notes families
    if "level" in cols:
        payload["level"] = level_val
    if "estimated_level" in cols:
        payload["estimated_level"] = level_val
    if "tons_est" in cols:
        payload["tons_est"] = tons_val
    if "estimated_tons" in cols:
        payload["estimated_tons"] = tons_val
    if "notes" in cols:
        payload["notes"] = notes_val
    if "driver_notes" in cols:
        payload["driver_notes"] = notes_val

    if not payload:
        raise RuntimeError("inventory_estimates table has no writable columns")

    # Must satisfy NOT NULL on either level family
    if "estimated_level" in cols and "estimated_level" not in payload:
        payload["estimated_level"] = level_val
    if "level" in cols and "level" not in payload:
        payload["level"] = level_val

    col_names = list(payload.keys())
    placeholders = ", ".join("?" for _ in col_names)
    sql = (
        f"INSERT INTO inventory_estimates ({', '.join(col_names)}) "
        f"VALUES ({placeholders})"
    )
    cur = conn.execute(sql, tuple(payload[c] for c in col_names))
    estimate_id = int(cur.lastrowid)

    if lead_id is not None:
        lead_cols = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(leads)").fetchall()
        }
        sets: list[str] = []
        vals: list[Any] = []
        if "last_estimate_level" in lead_cols:
            sets.append("last_estimate_level = ?")
            vals.append(level_val)
        if "last_estimate_date" in lead_cols:
            sets.append("last_estimate_date = ?")
            vals.append(stamp)
        if "last_estimate_tons" in lead_cols:
            sets.append("last_estimate_tons = ?")
            vals.append(tons_val)
        if sets:
            vals.append(lead_id)
            conn.execute(
                f"UPDATE leads SET {', '.join(sets)} WHERE id = ?",
                tuple(vals),
            )

    return estimate_id


def _tons_expr(cols: set[str]) -> str:
    if "tons_est" in cols and "estimated_tons" in cols:
        return "COALESCE(tons_est, estimated_tons, 0)"
    if "tons_est" in cols:
        return "COALESCE(tons_est, 0)"
    if "estimated_tons" in cols:
        return "COALESCE(estimated_tons, 0)"
    return "0"


def _level_expr(cols: set[str], alias: str = "") -> str:
    p = f"{alias}." if alias else ""
    if "level" in cols and "estimated_level" in cols:
        return f"COALESCE({p}level, {p}estimated_level)"
    if "level" in cols:
        return f"{p}level"
    if "estimated_level" in cols:
        return f"{p}estimated_level"
    return "NULL"


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

    cols = ensure_inventory_estimate_columns(conn)
    tons_sql = _tons_expr(cols)
    est_row = conn.execute(
        f"""
        SELECT {tons_sql} AS tons_est FROM inventory_estimates
        WHERE lead_id = ?
        ORDER BY COALESCE(created_at, estimate_date) DESC, id DESC
        LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    if est_row is None:
        return None

    estimated_tons = float(est_row["tons_est"] or 0)
    days = (estimated_tons / avg_weekly_tons) * 7.0
    days = round(days, 1)

    conn.execute(
        "UPDATE leads SET days_of_supply_est = ? WHERE id = ?",
        (days, lead_id),
    )
    return days


def get_lead_inventory_latest(conn: Any, lead_id: int) -> dict[str, Any] | None:
    """Return the most recent inventory estimate for a lead as a dict."""
    cols = ensure_inventory_estimate_columns(conn)
    row = conn.execute(
        """
        SELECT * FROM inventory_estimates
        WHERE lead_id = ?
        ORDER BY COALESCE(created_at, estimate_date) DESC, id DESC
        LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    # Normalize dual-schema fields for callers
    level = data.get("level") or data.get("estimated_level")
    tons = data.get("tons_est")
    if tons is None:
        tons = data.get("estimated_tons")
    notes = data.get("notes") or data.get("driver_notes")
    data["level"] = level
    data["tons_est"] = float(tons or 0)
    data["notes"] = notes or ""
    data["estimated_level"] = level
    data["estimated_tons"] = float(tons or 0)
    data["driver_notes"] = notes or ""
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
        name = getattr(f, "name", "photo.bin") or "photo.bin"
        # camera_input often returns name like "camera.jpg" — keep unique
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe = str(name).replace(" ", "_").replace("/", "_").replace("\\", "_")
        fname = f"inv_{lead_id or 0}_{load_id or 0}_{stamp}_{safe}"
        dest = INVENTORY_PHOTOS_DIR / fname
        dest.write_bytes(raw)
        saved.append(str(dest))
    return saved


def days_of_supply_color(days: float | None) -> str:
    """Return a hex color based on days of supply remaining."""
    if days is None:
        return "#94a3b8"  # gray
    if days >= 14:
        return "#4ade80"  # green
    if days >= 7:
        return "#fbbf24"  # yellow
    return "#f87171"  # red


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


def inventory_estimates_select_sql(
    cols: set[str] | None = None,
    *,
    where_lead: bool = False,
    limit: int | None = None,
) -> str:
    """Build a SELECT that works on both legacy and canonical inventory schemas."""
    # Prefer COALESCE when both column families exist; fall back otherwise.
    # Callers without a live conn can pass None and use safe defaults for fresh DBs.
    if cols is None:
        cols = {
            "id",
            "lead_id",
            "estimate_date",
            "level",
            "tons_est",
            "notes",
            "photo_paths",
            "created_at",
            "estimated_by",
            "commodity",
        }

    level_e = _level_expr(cols, "ie")
    if "tons_est" in cols and "estimated_tons" in cols:
        tons_e = "COALESCE(ie.tons_est, ie.estimated_tons)"
    elif "tons_est" in cols:
        tons_e = "ie.tons_est"
    elif "estimated_tons" in cols:
        tons_e = "ie.estimated_tons"
    else:
        tons_e = "NULL"

    if "notes" in cols and "driver_notes" in cols:
        notes_e = "COALESCE(ie.notes, ie.driver_notes)"
    elif "notes" in cols:
        notes_e = "ie.notes"
    elif "driver_notes" in cols:
        notes_e = "ie.driver_notes"
    else:
        notes_e = "NULL"

    if "estimate_date" in cols and "created_at" in cols:
        date_e = "COALESCE(ie.estimate_date, ie.created_at)"
    elif "estimate_date" in cols:
        date_e = "ie.estimate_date"
    elif "created_at" in cols:
        date_e = "ie.created_at"
    else:
        date_e = "NULL"

    photo_e = "ie.photo_paths" if "photo_paths" in cols else "NULL"
    by_e = "ie.estimated_by" if "estimated_by" in cols else "NULL"
    created_e = "ie.created_at" if "created_at" in cols else "NULL"
    commodity_e = "ie.commodity" if "commodity" in cols else "NULL"

    where = "WHERE ie.lead_id = ?" if where_lead else ""
    limit_sql = f"LIMIT {int(limit)}" if limit else ""

    return f"""
        SELECT ie.id, ie.lead_id,
               {date_e} AS estimate_date,
               {level_e} AS level,
               {tons_e} AS tons_est,
               {notes_e} AS notes,
               {photo_e} AS photo_paths,
               {created_e} AS created_at,
               {by_e} AS estimated_by,
               {commodity_e} AS commodity,
               ld.company AS shipper
        FROM inventory_estimates ie
        LEFT JOIN leads ld ON ie.lead_id = ld.id
        {where}
        ORDER BY {date_e} DESC, ie.id DESC
        {limit_sql}
    """
