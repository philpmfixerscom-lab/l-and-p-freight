"""Live fleet view: vehicle telemetry + active loads + deadhead watch.

Pulls in-cab telemetry from the ELD layer (currently the stub provider; swap in a
real Samsara/Motive provider behind the same facade) and combines it with active
loads so the Dashboard/Maps screen can show a real-time command center.
"""

from __future__ import annotations

from typing import Any

from lp_helpers.database import get_conn
from eld_integration import ELDClient, StubEldProvider

ACTIVE_STATUSES = ("Accepted", "In Transit", "Delivered")


def get_fleet_view(conn=None) -> dict[str, Any]:
    """Return vehicle telemetry plus active loads and a deadhead watch list."""
    own = conn is None
    if own:
        conn = get_conn()
    try:
        client = ELDClient()
        loc = client.get_vehicle_location(StubEldProvider.VEHICLE_ID)
        moving = (loc.speed_mph or 0.0) > 0.5
        vehicle = {
            "vehicle_id": StubEldProvider.VEHICLE_ID,
            "lat": loc.lat,
            "lon": loc.lon,
            "speed_mph": loc.speed_mph,
            "heading_deg": loc.heading_deg,
            "reported_at": loc.reported_at,
            "status": "Moving" if moving else "Idle",
        }

        rows = conn.execute(
            """
            SELECT id, bol_number, shipper, commodity, origin, destination,
                   deadhead_miles, loaded_miles, total_revenue, status
            FROM loads
            WHERE status IN (?, ?, ?)
            ORDER BY pickup_date DESC
            """,
            ACTIVE_STATUSES,
        ).fetchall()
        active_loads = [dict(r) for r in rows]

        watch: list[dict[str, Any]] = []
        for r in active_loads:
            dead = float(r.get("deadhead_miles") or 0.0)
            loaded = float(r.get("loaded_miles") or 0.0)
            total = dead + loaded
            share = round(dead / total, 3) if total > 0 else 0.0
            watch.append({**dict(r), "deadhead_share": share})
        watch.sort(key=lambda x: x["deadhead_share"], reverse=True)
        watch = [w for w in watch if w["deadhead_share"] >= 0.35][:5]

        return {
            "vehicle": vehicle,
            "active_loads": active_loads,
            "deadhead_watch": watch,
            "demo": True,
        }
    finally:
        if own:
            conn.close()
