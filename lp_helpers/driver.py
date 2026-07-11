"""Driver-facing view: HOS, load acceptance, route/pay, BOL capture.

Built as a role-specific mobile screen on top of the same data the dispatcher
uses, so the driver can accept loads, see pay on actual miles, and upload the
signed BOL — while the customer billing goes live the moment a load is accepted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lp_helpers.database import DB_PATH, get_conn
from eld_integration import ELDClient, StubEldProvider

ACTIVE_STATUSES = ("Accepted", "In Transit", "Delivered")


def get_driver_hos() -> dict[str, Any]:
    client = ELDClient()
    h = client.get_driver_hos(StubEldProvider.DRIVER_ID)
    return {
        "driver_name": h.driver_name,
        "hours_today": h.hours_today,
        "hours_week": h.hours_week,
        "drive_remaining_hours": h.drive_remaining_hours,
        "on_duty_remaining_hours": h.on_duty_remaining_hours,
        "cycle_remaining_hours": h.cycle_remaining_hours,
        "violation": h.violation,
        "updated_at": h.updated_at,
    }


def get_driver_loads(conn=None) -> dict[str, list[dict[str, Any]]]:
    own = conn is None
    if own:
        conn = get_conn()
    try:
        pending = [
            dict(r) for r in conn.execute(
                "SELECT id, bol_number, shipper, commodity, origin, destination, total_revenue, status, pickup_date "
                "FROM loads WHERE status = 'Logged' ORDER BY pickup_date DESC"
            ).fetchall()
        ]
        active = [
            dict(r) for r in conn.execute(
                "SELECT id, bol_number, shipper, commodity, origin, destination, total_revenue, status, "
                "pickup_date, accepted_at, bol_photo_path, deadhead_miles, loaded_miles "
                "FROM loads WHERE status IN ('Accepted','In Transit','Delivered') ORDER BY pickup_date DESC"
            ).fetchall()
        ]
        return {"pending": pending, "active": active}
    finally:
        if own:
            conn.close()


def accept_load(load_id: int, status: str = "Accepted") -> None:
    """Driver accepts a load: stamps accepted_at, flips customer billing live, queues invoice."""
    from lp_helpers.billing import queue_invoice

    conn = get_conn()
    try:
        conn.execute(
            "UPDATE loads SET status = ?, accepted_at = datetime('now') "
            "WHERE id = ? AND accepted_at IS NULL",
            (status, load_id),
        )
        conn.execute("UPDATE po_loads SET status = 'In Transit' WHERE load_id = ?", (load_id,))
        conn.commit()
    finally:
        conn.close()
    queue_invoice(load_id)


def save_bol_photo(load_id: int, filename: str, data: bytes) -> str:
    """Persist an uploaded signed-BOL photo and record its path on the load."""
    folder = Path(DB_PATH).parent / "bol_photos"
    folder.mkdir(parents=True, exist_ok=True)
    safe = f"{load_id}_{Path(filename).name}"
    path = folder / safe
    path.write_bytes(data)
    conn = get_conn()
    try:
        conn.execute("UPDATE loads SET bol_photo_path = ? WHERE id = ?", (str(path), load_id))
        conn.commit()
    finally:
        conn.close()
    return str(path)
