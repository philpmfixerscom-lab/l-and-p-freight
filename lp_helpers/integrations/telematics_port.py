"""Provider-agnostic telematics port (no vendor lock-in).

Domain code depends on TelematicsPort + LiveFix only.
Adapters: Traccar, Manual/sim, future Motive/Samsara.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class LiveFix:
    device_id: str | int | None
    device_name: str
    latitude: float
    longitude: float
    speed_mph: float
    heading: float = 0.0
    recorded_at: str | None = None
    provider: str = "unknown"
    raw: dict[str, Any] | None = None


@dataclass
class ConnectionStatus:
    ok: bool
    provider: str
    mode: str
    message: str = ""


@dataclass
class DeviceInfo:
    provider_device_id: str
    name: str
    status: str = "unknown"


@runtime_checkable
class TelematicsPort(Protocol):
    def connection_status(self) -> ConnectionStatus: ...

    def list_devices(self) -> list[DeviceInfo]: ...

    def get_live_fix(self, device_id: str | int | None = None) -> LiveFix | None: ...


class ManualTelematicsAdapter:
    """Yard / offline fallback — no network required."""

    def __init__(
        self,
        *,
        lat: float = 35.912,
        lon: float = -82.064,
        label: str = "Spruce Pine Yard",
    ) -> None:
        self.lat = lat
        self.lon = lon
        self.label = label

    def connection_status(self) -> ConnectionStatus:
        return ConnectionStatus(
            ok=True,
            provider="manual",
            mode="yard",
            message="Using yard coordinates (no live GPS provider).",
        )

    def list_devices(self) -> list[DeviceInfo]:
        return [DeviceInfo(provider_device_id="yard", name=self.label, status="online")]

    def get_live_fix(self, device_id: str | int | None = None) -> LiveFix | None:
        return LiveFix(
            device_id="yard",
            device_name=self.label,
            latitude=self.lat,
            longitude=self.lon,
            speed_mph=0.0,
            recorded_at=datetime.now().isoformat(timespec="seconds"),
            provider="manual",
        )


class TraccarTelematicsAdapter:
    """Adapter over existing TraccarLive client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def connection_status(self) -> ConnectionStatus:
        try:
            status = self._client.connection_status()
            return ConnectionStatus(
                ok=bool(status.get("ok")),
                provider="traccar",
                mode=str(status.get("mode") or "live"),
                message=str(status.get("message") or ""),
            )
        except Exception as exc:
            return ConnectionStatus(
                ok=False, provider="traccar", mode="error", message=str(exc)
            )

    def list_devices(self) -> list[DeviceInfo]:
        try:
            devices = self._client.fetch_devices()
        except Exception:
            return []
        out: list[DeviceInfo] = []
        for d in devices or []:
            out.append(
                DeviceInfo(
                    provider_device_id=str(d.get("id")),
                    name=str(d.get("name") or f"Device {d.get('id')}"),
                    status=str(d.get("status") or "unknown"),
                )
            )
        return out

    def get_live_fix(self, device_id: str | int | None = None) -> LiveFix | None:
        try:
            did = int(device_id) if device_id is not None and str(device_id).isdigit() else None
            fix = self._client.get_live_status(did)
        except Exception:
            return None
        if not fix or fix.get("latitude") is None:
            return None
        return LiveFix(
            device_id=fix.get("device_id"),
            device_name=str(fix.get("device_name") or "device"),
            latitude=float(fix["latitude"]),
            longitude=float(fix["longitude"]),
            speed_mph=float(fix.get("speed_mph") or 0),
            heading=float(fix.get("course") or 0),
            recorded_at=str(fix.get("fix_time") or "") or None,
            provider="traccar",
            raw=fix.get("raw") if isinstance(fix.get("raw"), dict) else fix,
        )


def get_telematics_port(*, get_secret: Any | None = None) -> TelematicsPort:
    """Factory: prefer Traccar when configured, else Manual yard."""
    if get_secret is None:
        return ManualTelematicsAdapter()
    try:
        from lp_helpers.traccar_live import TraccarLive

        client = TraccarLive(get_secret=get_secret)
        adapter = TraccarTelematicsAdapter(client)
        status = adapter.connection_status()
        if status.ok:
            return adapter
        # Try a live fix even if connection_status is soft-fail
        if adapter.get_live_fix() is not None:
            return adapter
    except Exception:
        pass
    return ManualTelematicsAdapter()
