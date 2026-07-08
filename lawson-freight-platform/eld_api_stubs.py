"""
API stubs for real ELD providers.

These classes show the exact methods / payload shapes each vendor
integration must implement. Swap the stub provider in eld_integration.ELDClient
for a real one when credentials are available.
"""

from __future__ import annotations

from typing import Any

from eld_integration import EldProvider, VehicleLocation, DriverHos


# ===========================================================================
# Samsara
# ===========================================================================


class SamsaraProvider(EldProvider):
    """
    Samsara API reference:
    https://developers.samsara.com/reference/get-fleet-vehicles-locations
    """

    def __init__(self, api_token: str, base_url: str = "https://api.samsara.com") -> None:
        self.api_token = api_token
        self.base_url = base_url

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}", "Accept": "application/json"}

    def get_vehicle_location(self, vehicle_id: str) -> VehicleLocation:
        # Real impl:
        # resp = requests.get(f"{self.base_url}/fleet/vehicles/locations", headers=self._headers(), params={"vehicleId": vehicle_id})
        # data = resp.json()
        # return VehicleLocation(lat=data["lat"], lon=data["lng"], speed_mph=data["speedMilesPerHour"], ...)
        raise NotImplementedError("Samsara provider requires real API token and network access.")

    def get_driver_hos(self, driver_id: str) -> DriverHos:
        raise NotImplementedError("Use Samsara HOS endpoint once provisioned.")

    def push_dispatch(self, driver_id: str, load: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Use Samsara messaging / dispatch endpoint.")

    def ack_bill_of_lading(self, driver_id: str, bol_number: str) -> dict[str, Any]:
        raise NotImplementedError("Use Samsara driver app / webhook.")


# ===========================================================================
# Motive
# ===========================================================================


class MotiveProvider(EldProvider):
    """
    Motive (KeepTruckin') API reference:
    https://developer.motive.com/api/
    """

    def __init__(self, api_key: str, base_url: str = "https://api.motive.com/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url

    def get_vehicle_location(self, vehicle_id: str) -> VehicleLocation:
        raise NotImplementedError("Motive provider requires real API key.")

    def get_driver_hos(self, driver_id: str) -> DriverHos:
        raise NotImplementedError("Use Motive /eld_logs endpoint.")

    def push_dispatch(self, driver_id: str, load: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Use Motive /messages endpoint.")

    def ack_bill_of_lading(self, driver_id: str, bol_number: str) -> dict[str, Any]:
        raise NotImplementedError("Use Motive /documents endpoint.")


# ===========================================================================
# Geotab
# ===========================================================================


class GeotabProvider(EldProvider):
    """
    Geotab API reference:
    https://geotab.github.io/sdk/guides/gettingstarted/
    """

    def __init__(self, username: str, password: str, database: str, server: str) -> None:
        self.username = username
        self.password = password
        self.database = database
        self.server = server

    def get_vehicle_location(self, vehicle_id: str) -> VehicleLocation:
        raise NotImplementedError("Geotab provider requires authenticated SDK session.")

    def get_driver_hos(self, driver_id: str) -> DriverHos:
        raise NotImplementedError("Use Geotab StatusData / DutyStatusAvailability.")

    def push_dispatch(self, driver_id: str, load: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Use Geotab messaging / exception rules.")

    def ack_bill_of_lading(self, driver_id: str, bol_number: str) -> dict[str, Any]:
        raise NotImplementedError("Use Geotab custom device data or webhook.")


# ===========================================================================
# Internal ingestion helpers
# ===========================================================================


def ingest_eld_miles(load_id: int, actual_loaded: float, actual_empty: float, source: str = "eld") -> None:
    """
    Persist actual miles from ELD into routes table for settlement fairness.
    """
    from routing_editor import fetch_routes, update_route_actuals
    routes = fetch_routes(load_id=load_id)
    if routes.empty:
        return
    route_id = int(routes.iloc[0]["id"])
    update_route_actuals(route_id, actual_loaded, actual_empty)


def create_eld_webhook(payload: dict[str, Any]) -> None:
    """
    Entrypoint for vendor webhooks (Samsara/Motive/Geotab).

    Expected shape:
    {
      "provider": "samsara|motive|geotab",
      "event": "location_update|hos_update|bol_ack",
      "vehicle_id": "...",
      "driver_id": "...",
      "load_id": "...",
      "data": { ... }
    }
    """
    from eld_integration import _log_eld_event
    _log_eld_event("webhook", payload)
