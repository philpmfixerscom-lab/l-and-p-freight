"""Live Traccar GPS fleet integration — session login, API token, multi-device map."""

from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Any, Callable

log = logging.getLogger("lawson_freight.traccar")

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


class TraccarLive:
    """Traccar REST client — email/password session or Bearer API token."""

    def __init__(
        self,
        *,
        get_secret: Callable[[str, str, str], str],
        url: str | None = None,
        api_token: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ) -> None:
        self.base_url = (url or get_secret("traccar", "url", "http://localhost:8082")).rstrip("/")
        self.api_token = (api_token or get_secret("traccar", "api_token", "")).strip()
        self.email = email or get_secret("traccar", "email", "admin")
        self.password = password or get_secret("traccar", "password", "admin")
        self.preferred_device_id = get_secret("traccar", "device_id", "").strip()
        self._session = requests.Session() if requests else None
        self._device_names: dict[int, str] = {}
        self._session_logged_in = False

    @property
    def configured(self) -> bool:
        return bool(self.base_url and requests is not None)

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_token:
            return {}
        if ":" in self.api_token and not self.api_token.startswith("Bearer "):
            encoded = base64.b64encode(self.api_token.encode("utf-8")).decode("ascii")
            return {"Authorization": f"Basic {encoded}"}
        token = self.api_token.removeprefix("Bearer ").strip()
        return {"Authorization": f"Bearer {token}"}

    def _login(self) -> None:
        if self.api_token:
            return
        if self._session_logged_in:
            return
        if not self._session:
            raise RuntimeError("requests package not installed")
        resp = self._session.post(
            f"{self.base_url}/api/session",
            data={"email": self.email, "password": self.password},
            timeout=10,
        )
        resp.raise_for_status()
        self._session_logged_in = True

    def _api_get(self, path: str, **params: Any) -> requests.Response:
        if not self._session:
            raise RuntimeError("requests package not installed")
        headers = self._auth_headers()
        if not self.api_token:
            self._login()
        resp = self._session.get(
            f"{self.base_url}{path}",
            headers=headers,
            params=params or None,
            timeout=10,
        )
        resp.raise_for_status()
        return resp

    def connection_status(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "ok": False,
                "mode": "unconfigured",
                "message": "Add [traccar] to secrets.toml and install requests",
            }
        try:
            resp = self._api_get("/api/server")
            server = resp.json() if resp.content else {}
            return {
                "ok": True,
                "mode": "live",
                "message": f"Connected to {self.base_url}",
                "version": server.get("version", "unknown"),
            }
        except Exception as exc:
            log.info("Traccar connection failed: %s", exc)
            return {"ok": False, "mode": "offline", "message": str(exc)}

    def fetch_devices(self) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        try:
            data = self._api_get("/api/devices").json()
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
            params: dict[str, Any] = {}
            if device_id is not None:
                params["deviceId"] = device_id
            data = self._api_get("/api/positions", **params).json()
            return data if isinstance(data, list) else []
        except Exception as exc:
            log.info("Traccar positions fetch failed: %s", exc)
            return []

    def fetch_fleet(self) -> list[dict[str, Any]]:
        """All devices merged with latest positions for fleet map."""
        devices = self.fetch_devices()
        if not devices:
            return []
        positions = self.fetch_positions()
        pos_map: dict[int, dict[str, Any]] = {}
        for pos in positions:
            did = pos.get("deviceId")
            if did is not None:
                pos_map[int(did)] = pos

        fleet: list[dict[str, Any]] = []
        for d in devices:
            did = int(d["id"])
            name = str(d.get("name") or f"Device {did}")
            status = str(d.get("status") or "unknown")
            pos = pos_map.get(did)
            entry: dict[str, Any] = {
                "device_id": did,
                "device_name": name,
                "status": status,
                "latitude": None,
                "longitude": None,
                "speed_mph": 0.0,
                "course": 0.0,
                "fix_time": None,
            }
            if pos:
                speed_knots = float(pos.get("speed", 0) or 0)
                entry.update(
                    {
                        "latitude": float(pos.get("latitude", 0)),
                        "longitude": float(pos.get("longitude", 0)),
                        "speed_mph": speed_knots * 1.15078,
                        "course": float(pos.get("course", 0) or 0),
                        "fix_time": pos.get("fixTime") or pos.get("deviceTime"),
                        "raw": pos,
                    }
                )
            fleet.append(entry)
        return fleet

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

    def get_live_fix(self, device_id: int | None = None) -> dict[str, Any] | None:
        fleet = self.fetch_fleet()
        if not fleet:
            return None
        if device_id is not None:
            matches = [f for f in fleet if f["device_id"] == device_id and f["latitude"] is not None]
        else:
            matches = [f for f in fleet if f["latitude"] is not None]
            preferred = self.resolve_device_id(
                [{"id": f["device_id"], "status": f["status"]} for f in fleet]
            )
            if preferred:
                matches = [f for f in matches if f["device_id"] == preferred] or matches
        if not matches:
            return None
        fix = matches[0]
        return {
            "device_id": fix["device_id"],
            "device_name": fix["device_name"],
            "latitude": fix["latitude"],
            "longitude": fix["longitude"],
            "speed_mph": fix["speed_mph"],
            "course": fix.get("course", 0),
            "fix_time": fix.get("fix_time") or datetime.now().isoformat(),
            "raw": fix.get("raw"),
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