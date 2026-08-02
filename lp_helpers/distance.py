"""Optional road-mile estimates via public OSRM (no API key).

Soft-fails always — callers fall back to keyword heuristics in deadhead.py.
"""

from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("lawson_freight.distance")

# Module-level 24h cache: key (lat1,lon1,lat2,lon2 rounded) -> (miles, epoch)
_MILES_CACHE: dict[tuple[float, float, float, float], tuple[float, float]] = {}
_CACHE_TTL_SEC = 24 * 3600
_MAX_CACHE_ENTRIES = 256

# Known corridor cities for Spruce Pine ↔ Central GA bulk lane
CITY_LATLON: dict[str, tuple[float, float]] = {
    "spruce pine": (35.9154, -82.0646),
    "spruce pine, nc": (35.9154, -82.0646),
    "burnsville": (35.9173, -82.3010),
    "bakersville": (36.0157, -82.1587),
    "marion nc": (35.6840, -82.0093),
    "asheville": (35.5951, -82.5515),
    "asheville, nc": (35.5951, -82.5515),
    "hickory": (35.7345, -81.3445),
    "morganton": (35.7454, -81.6848),
    "lenoir": (35.9140, -81.5390),
    "boone": (36.2168, -81.6746),
    "western nc": (35.60, -82.55),
    "west nc": (35.60, -82.55),
    "north carolina": (35.76, -79.02),
    "greenville": (34.8526, -82.3940),
    "spartanburg": (34.9496, -81.9320),
    "greenville / spartanburg, sc": (34.90, -82.16),
    "anderson": (34.5034, -82.6501),
    "columbia sc": (34.0007, -81.0348),
    "macon": (32.8407, -83.6324),
    "macon, ga": (32.8407, -83.6324),
    "augusta": (33.4735, -82.0105),
    "augusta, ga": (33.4735, -82.0105),
    "athens": (33.9519, -83.3576),
    "atlanta": (33.7490, -84.3880),
    "warner robins": (32.6130, -83.6242),
    "milledgeville": (33.0801, -83.2321),
    "dublin": (32.5404, -82.9038),
    "sandersville": (32.9815, -82.8101),
    "griffin": (33.2468, -84.2641),
    "columbus": (32.4610, -84.9877),
    "savannah": (32.0809, -81.0912),
    "kohler": (32.98, -82.72),
    "kohler area": (32.98, -82.72),
    "central georgia": (32.98, -82.72),
    "central georgia (kohler area)": (32.98, -82.72),
    "central ga": (32.98, -82.72),
    "georgia": (32.98, -82.72),
    "johnson city": (36.3134, -82.3535),
    "kingsport": (36.5484, -82.5618),
    "bristol": (36.5951, -82.1887),
}

OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"


def geocode_city(label: str) -> tuple[float, float] | None:
    """Map a free-text place label to (lat, lon) via known corridor dict.

    Prefers exact match, then first-token exact, then longest substring containment.
    """
    if not label:
        return None
    raw = str(label).strip().lower()
    if not raw:
        return None
    # 1) Exact key
    if raw in CITY_LATLON:
        return CITY_LATLON[raw]
    # 2) First city token exact (e.g. "Macon, GA area" → "macon")
    first = raw.split(",")[0].strip()
    if first and first in CITY_LATLON:
        return CITY_LATLON[first]
    # 3) Longest key contained in label (or label contained in key) — prefer longer keys
    best_key = None
    best_len = 0
    for key in CITY_LATLON:
        if len(key) < 4:
            continue  # skip very short keys to reduce false positives
        if key in raw or (len(raw) >= 4 and raw in key):
            if len(key) > best_len:
                best_key = key
                best_len = len(key)
    if best_key is not None:
        return CITY_LATLON[best_key]
    return None


def _cache_key(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> tuple[float, float, float, float]:
    return (round(lat1, 4), round(lon1, 4), round(lat2, 4), round(lon2, 4))


def _cache_get(key: tuple[float, float, float, float]) -> float | None:
    hit = _MILES_CACHE.get(key)
    if not hit:
        return None
    miles, ts = hit
    if time.time() - ts > _CACHE_TTL_SEC:
        _MILES_CACHE.pop(key, None)
        return None
    return miles


def _cache_set(key: tuple[float, float, float, float], miles: float) -> None:
    if len(_MILES_CACHE) >= _MAX_CACHE_ENTRIES:
        # Drop oldest ~25% by timestamp
        ordered = sorted(_MILES_CACHE.items(), key=lambda kv: kv[1][1])
        for k, _ in ordered[: max(1, _MAX_CACHE_ENTRIES // 4)]:
            _MILES_CACHE.pop(k, None)
    _MILES_CACHE[key] = (miles, time.time())


def clear_distance_cache() -> None:
    """Test helper."""
    _MILES_CACHE.clear()


def fetch_osrm_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    timeout: float = 4.0,
) -> float | None:
    """Query public OSRM for driving distance in miles. Soft-fail → None."""
    key = _cache_key(lat1, lon1, lat2, lon2)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    url = f"{OSRM_BASE}/{lon1},{lat1};{lon2},{lat2}?overview=false"
    try:
        import requests

        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
        routes = data.get("routes") or []
        if not routes:
            return None
        meters = float(routes[0].get("distance") or 0)
        if meters <= 0:
            return None
        miles = round(meters / 1609.344, 1)
        _cache_set(key, miles)
        return miles
    except Exception as exc:
        log.debug("OSRM unavailable: %s", exc)
        return None


def estimate_road_miles(a: str, b: str, *, timeout: float = 4.0) -> float | None:
    """Road miles between two place labels when both geocode; else None.

    Never raises. Uses OSRM public API + CITY_LATLON map.
    """
    c1 = geocode_city(a)
    c2 = geocode_city(b)
    if c1 is None or c2 is None:
        return None
    if c1 == c2:
        return 0.0
    return fetch_osrm_miles(c1[0], c1[1], c2[0], c2[1], timeout=timeout)


def estimate_empty_home_miles_hybrid(
    current_location: str,
    home: str,
    *,
    heuristic_fn: Any | None = None,
) -> tuple[float, str]:
    """Prefer OSRM road miles; fall back to heuristic. Returns (miles, source)."""
    road = estimate_road_miles(current_location, home)
    if road is not None and road > 0:
        return road, "osrm"
    if heuristic_fn is not None:
        return float(heuristic_fn(current_location, home)), "heuristic"
    try:
        from lp_helpers.deadhead import estimate_empty_home_miles

        return float(estimate_empty_home_miles(current_location, home)), "heuristic"
    except Exception:
        return 250.0, "heuristic"
