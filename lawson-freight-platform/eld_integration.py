"""
ELD / Hardware Integration Layer for L & P Freight.

Providers (placeholder):
- Samsara
- Motive (formerly KeepTruckin')
- Trimble
- Geotab

This module exposes a single facade: ELDClient
It currently uses local stubs so the rest of the system can be built
before real vendor accounts are provisioned.
"""

from __future__ import annotations

import math
import random
import time
from datetime import date, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from lp_helpers.database import get_conn


# ===========================================================================
# Domain types
# ===========================================================================


class VehicleLocation:
    def __init__(
        self,
        lat: float,
        lon: float,
        speed_mph: float = 0.0,
        heading_deg: float = 0.0,
        reported_at: str | None = None,
    ):
        self.lat = float(lat)
        self.lon = float(lon)
        self.speed_mph = float(speed_mph)
        self.heading_deg = float(heading_deg)
        self.reported_at = reported_at or datetime.now().isoformat(timespec="seconds")


class DriverHos:
    def __init__(
        self,
        driver_name: str,
        hours_today: float = 0.0,
        hours_week: float = 0.0,
        drive_remaining_hours: float = 11.0,
        on_duty_remaining_hours: float = 14.0,
        cycle_remaining_hours: float = 60.0,
        break_required_in_hours: float | None = None,
        violation: bool = False,
        updated_at: str | None = None,
    ):
        self.driver_name = driver_name
        self.hours_today = hours_today
        self.hours_week = hours_week
        self.drive_remaining_hours = drive_remaining_hours
        self.on_duty_remaining_hours = on_duty_remaining_hours
        self.cycle_remaining_hours = cycle_remaining_hours
        self.break_required_in_hours = break_required_in_hours
        self.violation = violation
        self.updated_at = updated_at or datetime.now().isoformat(timespec="seconds")


# ===========================================================================
# Provider protocol  (real vendors implement this)
# ===========================================================================


class EldProvider(Protocol):
    def get_vehicle_location(self, vehicle_id: str) -> VehicleLocation: ...
    def get_driver_hos(self, driver_id: str) -> DriverHos: ...
    def push_dispatch(self, driver_id: str, load: dict[str, Any]) -> dict[str, Any]: ...
    def ack_bill_of_lading(self, driver_id: str, bol_number: str) -> dict[str, Any]: ...


# ===========================================================================
# Stub implementations (no network)
# ===========================================================================


class StubEldProvider(EldProvider):
    VEHICLE_ID = "TRUCK-1"
    DRIVER_ID = "driver-1"

    def get_vehicle_location(self, vehicle_id: str) -> VehicleLocation:
        if vehicle_id != self.VEHICLE_ID:
            raise KeyError(f"Unknown vehicle {vehicle_id}")
        return VehicleLocation(
            lat=35.912 + random.uniform(-0.01, 0.01),
            lon=-82.064 + random.uniform(-0.01, 0.01),
            speed_mph=random.choice([0.0, 45.0, 55.0, 65.0, 0.0]),
            heading_deg=random.uniform(0.0, 360.0),
        )

    def get_driver_hos(self, driver_id: str) -> DriverHos:
        return DriverHos(
            driver_name="Phillip / Lawson",
            hours_today=round(random.uniform(1.0, 8.0), 1),
            hours_week=round(random.uniform(10.0, 55.0), 1),
            drive_remaining_hours=round(random.uniform(1.0, 11.0), 1),
            on_duty_remaining_hours=round(random.uniform(2.0, 14.0), 1),
            cycle_remaining_hours=round(random.uniform(5.0, 60.0), 1),
            break_required_in_hours=round(random.uniform(0.5, 8.0), 1) if random.random() < 0.4 else None,
            violation=False,
        )

    def push_dispatch(self, driver_id: str, load: dict[str, Any]) -> dict[str, Any]:
        bol = load.get("bol_number") or f"LP-{datetime.now().strftime('%Y%m%d%H%M')}"
        return {
            "status": "delivered_to_device",
            "driver_id": driver_id,
            "bol_number": bol,
            " delivered_at": datetime.now().isoformat(timespec="seconds"),
        }

    def ack_bill_of_lading(self, driver_id: str, bol_number: str) -> dict[str, Any]:
        return {
            "status": "accepted",
            "driver_id": driver_id,
            "bol_number": bol_number,
            "accepted_at": datetime.now().isoformat(timespec="seconds"),
        }


# ===========================================================================
# ELD client facade used by the rest of the app
# ===========================================================================


class ELDClient:
    def __init__(self) -> None:
        self.provider = StubEldProvider()
        self._cache: dict[str, Any] = {}

    def set_provider(self, provider: EldProvider) -> None:
        self.provider = provider

    def get_vehicle_location(self, vehicle_id: str) -> VehicleLocation:
        return self.provider.get_vehicle_location(vehicle_id)

    def get_driver_hos(self, driver_id: str) -> DriverHos:
        return self.provider.get_driver_hos(driver_id)

    def push_dispatch(self, driver_id: str, load: dict[str, Any]) -> dict[str, Any]:
        res = self.provider.push_dispatch(driver_id, load)
        _log_eld_event("push_dispatch", res)
        return res

    def ack_bill_of_lading(self, driver_id: str, bol_number: str) -> dict[str, Any]:
        res = self.provider.ack_bill_of_lading(driver_id, bol_number)
        _log_eld_event("ack_bol", res)
        return res


def _log_eld_event(event_type: str, payload: dict[str, Any]) -> None:
    try:
        conn = get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eld_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                payload TEXT,
                logged_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "INSERT INTO eld_events (event_type, payload) VALUES (?, ?)",
            (event_type, str(payload)),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
