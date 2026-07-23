"""BulkLoads.com live postings client — secrets-driven, local-first fallback.

Configure in .streamlit/secrets.toml:

    [bulkloads]
    api_key = "your_api_key"
    base_url = "https://api.bulkloads.com/v1"   # override when partner URL is issued
    enabled = "1"
    timeout_sec = "12"

Without credentials the client returns curated NC/GA market intel and
labels listings as cached/demo so dispatch never hard-fails.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import requests

log = logging.getLogger(__name__)

# Partner API path candidates (first 200 wins). Override with secrets bulkloads.search_path.
_DEFAULT_SEARCH_PATHS = (
    "/loads/search",
    "/api/v1/loads",
    "/loads",
)

# Equipment types L&P cares about for end-dump bulk
DEFAULT_EQUIPMENT = ("end dump", "end-dump", "dump", "hopper", "belly dump")


def _secret(section: str, key: str, default: str = "") -> str:
    """Read Streamlit secret, then env LP_BULKLOADS_*, then default."""
    try:
        import streamlit as st

        if section in st.secrets and key in st.secrets[section]:
            val = st.secrets[section][key]
            if val is not None and str(val).strip() != "":
                return str(val).strip()
    except Exception:
        pass
    env_key = f"LP_{section.upper()}_{key.upper()}"
    return os.environ.get(env_key, default).strip() or default


def bulkloads_config() -> dict[str, Any]:
    enabled_raw = _secret("bulkloads", "enabled", "1").lower()
    return {
        "api_key": _secret("bulkloads", "api_key") or _secret("bulkloads", "token"),
        "base_url": _secret(
            "bulkloads",
            "base_url",
            "https://api.bulkloads.com/v1",
        ).rstrip("/"),
        "search_path": _secret("bulkloads", "search_path", ""),
        "enabled": enabled_raw in ("1", "true", "yes", "on"),
        "timeout_sec": float(_secret("bulkloads", "timeout_sec", "12") or "12"),
        "origin_state": _secret("bulkloads", "origin_state", "NC"),
        "dest_state": _secret("bulkloads", "dest_state", "GA"),
    }


def is_live_configured() -> bool:
    cfg = bulkloads_config()
    return bool(cfg["enabled"] and cfg["api_key"])


def _normalize_listing(raw: dict[str, Any], *, source: str = "BulkLoads · Live") -> dict[str, Any]:
    """Map heterogeneous API payloads into the opportunities/intel shape."""
    origin = (
        raw.get("origin")
        or raw.get("origin_city")
        or raw.get("pickup_city")
        or raw.get("pickup")
        or ""
    )
    dest = (
        raw.get("destination")
        or raw.get("dest_city")
        or raw.get("delivery_city")
        or raw.get("drop")
        or ""
    )
    if origin and dest:
        lane = f"{origin} → {dest}"
    else:
        lane = str(raw.get("lane") or raw.get("route") or "Lane TBD")

    rate = raw.get("rate") or raw.get("rate_text") or raw.get("pay") or raw.get("price")
    if isinstance(rate, (int, float)):
        unit = str(raw.get("rate_unit") or raw.get("pay_unit") or "ton").lower()
        if unit in ("ton", "t", "/ton", "per ton"):
            rate = f"${float(rate):.0f}/ton"
        elif unit in ("load", "flat", "flatbed"):
            rate = f"${float(rate):,.0f} flat"
        else:
            rate = f"${float(rate):.2f}"
    rate = str(rate or "Rate on request")

    contact_parts = [
        raw.get("contact"),
        raw.get("contact_name"),
        raw.get("broker"),
        raw.get("company"),
        raw.get("phone"),
        raw.get("email"),
    ]
    contact = " · ".join(str(p) for p in contact_parts if p) or "See BulkLoads listing"

    posted = (
        raw.get("posted")
        or raw.get("posted_at")
        or raw.get("created_at")
        or raw.get("age")
        or "Today"
    )
    if isinstance(posted, (int, float)):
        posted = datetime.fromtimestamp(posted).strftime("%Y-%m-%d")

    commodity = str(
        raw.get("commodity")
        or raw.get("product")
        or raw.get("material")
        or "Bulk"
    )
    notes_bits = [
        raw.get("notes"),
        raw.get("equipment"),
        raw.get("equipment_type"),
        raw.get("weight"),
        raw.get("weight_tons") and f"{raw.get('weight_tons')}t",
        raw.get("external_id") and f"ID {raw.get('external_id')}",
    ]
    notes = " · ".join(str(b) for b in notes_bits if b)

    return {
        "source": source,
        "lane": lane,
        "commodity": commodity,
        "rate": rate,
        "contact": contact,
        "posted": str(posted),
        "notes": notes or "Live BulkLoads posting",
        "external_id": str(raw.get("id") or raw.get("load_id") or raw.get("external_id") or ""),
        "raw": raw,
    }


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("loads", "data", "results", "items", "postings", "listings"):
        val = payload.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict) and isinstance(val.get("items"), list):
            return [x for x in val["items"] if isinstance(x, dict)]
    return []


def fetch_live_postings(
    *,
    origin_state: str | None = None,
    dest_state: str | None = None,
    commodity: str | None = None,
    equipment: tuple[str, ...] | list[str] | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """
    Fetch live BulkLoads postings.

    Returns:
        {
          "ok": bool,
          "live": bool,
          "source": "api" | "fallback",
          "message": str,
          "fetched_at": iso str,
          "listings": [ normalized dicts ],
        }
    """
    from lp_helpers.load_board import NC_GA_MARKET_INTEL

    cfg = bulkloads_config()
    fetched_at = datetime.now().isoformat(timespec="seconds")
    origin_state = (origin_state or cfg["origin_state"] or "NC").upper()
    dest_state = (dest_state or cfg["dest_state"] or "GA").upper()
    equipment = equipment or DEFAULT_EQUIPMENT

    fallback_listings = []
    for x in NC_GA_MARKET_INTEL:
        row = dict(x)
        # Keep honest seed labels from load_board (never claim live)
        row["source"] = row.get("source") or "Lane Seed · Return"
        fallback_listings.append(row)

    fallback = {
        "ok": True,
        "live": False,
        "source": "fallback",
        "message": "Using curated NC/GA lane seeds (BulkLoads API not configured or unavailable).",
        "fetched_at": fetched_at,
        "listings": fallback_listings,
    }

    if not cfg["enabled"]:
        fallback["message"] = "BulkLoads API disabled in secrets (enabled=0)."
        return fallback

    if not cfg["api_key"]:
        fallback["message"] = (
            "No BulkLoads API key — add [bulkloads] api_key to .streamlit/secrets.toml."
        )
        return fallback

    params: dict[str, Any] = {
        "origin_state": origin_state,
        "destination_state": dest_state,
        "limit": limit,
    }
    if commodity:
        params["commodity"] = commodity
    if equipment:
        params["equipment"] = ",".join(equipment)

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "X-API-Key": cfg["api_key"],
        "Accept": "application/json",
        "User-Agent": "L&P-Freight-Platform/4.4",
    }

    paths = [cfg["search_path"]] if cfg["search_path"] else list(_DEFAULT_SEARCH_PATHS)
    last_error = ""

    for path in paths:
        if not path:
            continue
        url = f"{cfg['base_url']}{path if path.startswith('/') else '/' + path}"
        try:
            resp = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=cfg["timeout_sec"],
            )
            if resp.status_code == 404:
                last_error = f"404 at {path}"
                continue
            if resp.status_code in (401, 403):
                return {
                    "ok": False,
                    "live": False,
                    "source": "fallback",
                    "message": f"BulkLoads auth failed ({resp.status_code}). Check api_key.",
                    "fetched_at": fetched_at,
                    "listings": fallback["listings"],
                }
            resp.raise_for_status()
            items = _extract_items(resp.json())
            listings = [_normalize_listing(item) for item in items][:limit]
            if not listings:
                return {
                    "ok": True,
                    "live": True,
                    "source": "api",
                    "message": "BulkLoads API OK — no postings matched filters; showing fallback intel.",
                    "fetched_at": fetched_at,
                    "listings": fallback["listings"],
                }
            return {
                "ok": True,
                "live": True,
                "source": "api",
                "message": f"Live BulkLoads · {len(listings)} postings",
                "fetched_at": fetched_at,
                "listings": listings,
            }
        except requests.Timeout:
            last_error = f"timeout on {path}"
            log.warning("BulkLoads timeout: %s", url)
        except requests.RequestException as exc:
            last_error = str(exc)
            log.warning("BulkLoads request failed (%s): %s", url, exc)
        except ValueError as exc:
            last_error = f"invalid JSON: {exc}"
            log.warning("BulkLoads JSON error: %s", exc)

    fallback["ok"] = False
    fallback["message"] = f"BulkLoads API unreachable ({last_error}). Using curated intel."
    return fallback


def sync_postings_to_opportunities(conn, listings: list[dict[str, Any]]) -> tuple[int, int]:
    """Upsert normalized listings into opportunities. Returns (added, updated)."""
    from lp_helpers.load_board import (
        SOURCE_BULKLOADS_LIVE,
        ensure_opportunities_table,
        upsert_market_intel,
    )

    ensure_opportunities_table(conn)
    added = updated = 0
    for item in listings:
        src = item.get("source") or SOURCE_BULKLOADS_LIVE
        is_new = upsert_market_intel(
            conn,
            lane=item.get("lane", ""),
            commodity=item.get("commodity", "Bulk"),
            rate=item.get("rate", ""),
            contact=item.get("contact", ""),
            notes=item.get("notes", ""),
            source=src,
        )
        if is_new:
            added += 1
        else:
            updated += 1
    return added, updated
