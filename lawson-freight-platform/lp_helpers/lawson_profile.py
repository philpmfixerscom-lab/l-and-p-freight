"""Lawson / L & P Dispatch operation profile — single source of truth for lane, assets, and branding."""

from __future__ import annotations

from typing import Any

CARRIER_NAME = "L & P Dispatch"
PLATFORM_TITLE = "L & P Dispatch — Lawson Freight"
PAGE_TITLE = "L & P Dispatch | Lawson Freight"
TAGLINE = "Spruce Pine NC → Central GA · Phillip & Lawson"
MISSION_BLURB = (
    "Build loaded miles from Spruce Pine, NC to Central Georgia (Kohler area). "
    "Every empty mile is margin lost — prioritize backhauls, feldspar/quartz shippers "
    "on Hwy 19E & 226, and lane rates that cover fuel + deadhead."
)

DRIVERS: tuple[str, ...] = ("Phillip", "Lawson")
DEFAULT_OWNER = "Phillip"
TRUCK_LABEL = "L&P Lawson End-Dump"
TRAILER_DESC = "39ft Frameless End-Dump"
HIGHWAY_CORRIDORS = "Hwy 19E & 226"

# Loaded-mile share target for single-truck Lawson operation
LOADED_MILE_TARGET = 0.80

PRIMARY_RECEIVER = "Kohler Co."
PRIMARY_RECEIVER_NOTES = (
    "Primary Central GA delivery zone — Kohler area. "
    "Log arrivals for loaded-mile credit and backhaul planning."
)

LAWSON_SEED_LEADS: list[dict[str, Any]] = [
    {
        "company": "Sibelco Spruce Pine",
        "contact_name": "Dispatch",
        "phone": "828-592-2780",
        "email": "",
        "commodity_focus": "Quartz, Feldspar, Mica",
        "lane_notes": "Highway 19E, Spruce Pine, NC 28777 — High-purity quartz + feldspar/mica byproducts",
        "status": "Hot",
        "priority": 1,
    },
    {
        "company": "Covia",
        "contact_name": "Dispatch",
        "phone": "1-800-243-9004",
        "email": "",
        "commodity_focus": "Feldspar, Clay",
        "lane_notes": "7638 S Hwy 226, Spruce Pine, NC — Feldspar & minerals producer",
        "status": "Hot",
        "priority": 2,
    },
    {
        "company": "K-T Feldspar (The Quartz Corp)",
        "contact_name": "Dispatch",
        "phone": "828-765-9621",
        "email": "",
        "commodity_focus": "Feldspar",
        "lane_notes": "8342 Hwy 226 N, Spruce Pine, NC 28777 — Key feldspar shipper",
        "status": "Hot",
        "priority": 3,
    },
    {
        "company": "Feldspar Trucking (Trimac)",
        "contact_name": "Dispatch",
        "phone": "828-765-7491",
        "email": "",
        "commodity_focus": "Bulk / brokered",
        "lane_notes": "Local hauler — intel source for NC→GA backhauls",
        "status": "Active",
        "priority": 4,
    },
    {
        "company": PRIMARY_RECEIVER,
        "contact_name": "Receiving",
        "phone": "",
        "email": "dispatch@kohler.example",
        "commodity_focus": "Industrial delivery",
        "lane_notes": PRIMARY_RECEIVER_NOTES,
        "status": "Active",
        "priority": 5,
    },
]

LAWSON_GEOFENCES: list[tuple[str, float, float, float]] = [
    ("Spruce Pine Yard", 35.912, -82.064, 0.8),
    ("Kohler Central GA", 32.98, -82.72, 5.0),
]

LAWSON_SIM_ROUTE: list[tuple[float, float, str]] = [
    (35.912, -82.064, "Spruce Pine, NC — L&P Yard"),
    (35.650, -82.450, "Asheville corridor · I-26"),
    (35.200, -82.800, "I-26 southbound"),
    (34.500, -83.200, "Atlanta outskirts"),
    (33.447, -83.809, "Central Georgia — Kohler area"),
]