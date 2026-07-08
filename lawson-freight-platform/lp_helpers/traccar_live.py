"""Live Traccar GPS integration for L & P Dispatch — device pick, health check, telematics persist."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

log = logging.getLogger("lawson_freight.traccar")

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


class TraccarLive:
    """Traccar REST client with device resolution and connection diagnostics."""

    def __init__(
        self,
        *,
        get_secret: Callable[[str, str, str], str],
    ) -> None:
        self.base_url = get_secret("traccar", "url", "http://localhost:8082").rstrip("/")
        self.email = get_secret("traccar", "email", "admin")
        self.password = get_secret("traccar", "password", "admin")
        self.preferred_device_id = get_secret("traccar", "device_id", "").strip()
        self._session = requests.Session() if requests else None
        self._device_names: dict[int, str] = {}

    @property
    def configured(self) -> bool:
        return bool(self.base_url and requests is not None)

    def _login(self) -> None:
        if not self._session:
            raise RuntimeError("requests package not installed")
        resp = self._session.post(
            f"{self.base_url}/api/session",
            data={"email": self.email, "password": self.password},
            timeout=10,
        )
        resp.raise_for_status()

    def connection_status(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "ok": False,
                "mode": "unconfigured",
                "message": "Add [traccar] to secrets.toml and install requests",
            }
        try:
            self._login()
            resp = self._session.get(f"{self.base_url}/api/server", timeout=10)
            resp.raise_for_status()
            server = resp.json() if resp.content else {}
            return {
                "ok": True,
                "mode": "live",
                "message": f"Connected — {server.get('mapUrl', 'Traccar server')}",
                "version": server.get("version", "unknown"),
            }
        except Exception as exc:
            log.info("Traccar connection failed: %s", exc)
            return {"ok": False, "mode": "offline", "message": str(exc)}

    def fetch_devices(self) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        try:
            self._login()
            resp = self._session.get(f"{self.base_url}/api/devices", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            devices = data if isinstance(data, list) else []
            self._device_names = {
                int(d["id"]): str(d.get("name") or f"Device {d['id']}")
                for d in devices
                if d.get("id") is not None
            }
            return devices
        except Exception as exc:
            log.info("Traccar devices fetch failed: %s", exc)
            return []

    def fetch_positions(self, device_id: int | None = None) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        try:
            self._login()
            params: dict[str, Any] = {}
            if device_id is not None:
                params["deviceId"] = device_id
            resp = self._session.get(
                f"{self.base_url}/api/positions",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as exc:
            log.info("Traccar positions fetch failed: %s", exc)
            return []

    def resolve_device_id(self, devices: list[dict[str, Any]]) -> int | None:
        if self.preferred_device_id:
            try:
                return int(self.preferred_device_id)
            except ValueError:
                pass
        for d in devices:
            if d.get("status") == "online":
                return int(d["id"])
        if devices:
            return int(devices[0]["id"])
        return None

    def get_live_fix(
        self,
        device_id: int | None = None,
    ) -> dict[str, Any] | None:
        devices = self.fetch_devices()
        if device_id is None:
            device_id = self.resolve_device_id(devices)
        if device_id is None:
            return None
        positions = self.fetch_positions(device_id)
        if not positions:
            return None
        pos = positions[0]
        dev_id = int(pos.get("deviceId", device_id))
        name = self._device_names.get(dev_id, f"Device {dev_id}")
        speed_knots = float(pos.get("speed", 0) or 0)
        return {
            "device_id": dev_id,
            "device_name": name,
            "latitude": float(pos.get("latitude", 0)),
            "longitude": float(pos.get("longitude", 0)),
            "speed_mph": speed_knots * 1.15078,
            "course": float(pos.get("course", 0) or 0),
            "fix_time": pos.get("fixTime") or pos.get("deviceTime") or datetime.now().isoformat(),
            "raw": pos,
        }

    def persist_telematics(self, conn: Any, fix: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO telematics (
                recorded_at, latitude, longitude, speed_mph, notes
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(fix.get("fix_time", datetime.now().isoformat()))[:19],
                fix["latitude"],
                fix["longitude"],
                fix["speed_mph"],
                f"Traccar live — {fix.get('device_name', 'device')}",
            ),
        )
        conn.commit()