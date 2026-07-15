"""L & P Freight operation profile — lane, assets, and branding.

NOTE (multi-fleet roadmap): This module is the *current tenant default* for the
single L&P operation. Future multi-company support should load a TenantContext
(see lp_helpers/fleet_context.py) instead of hard-coding values here.
"""

from __future__ import annotations

from typing import Any

CARRIER_NAME = "L & P Freight"
# Legacy aliases kept for internal flags; never show to end users.
PLATFORM_EDITION = "Production"
PLATFORM_TAGLINE_INTERNAL = "Fewer empty miles. Clearer cash flow."
PLATFORM_TITLE = "L & P Freight Platform"
PAGE_TITLE = "L & P Freight"
# Public-facing tagline — O/O and small dispatch (not personal names)
TAGLINE = "Load more. Deadhead less. Get home."
MISSION_BLURB = (
    "Built for independent bulk haulers and small dispatch teams on regional lanes. "
    "Track loaded vs empty miles, quote by the ton, keep shippers warm, and run the cab "
    "without enterprise clutter — so more miles pay and more nights end at home."
)
MARKETING_HEADLINE = "Run your trucks. Not a mountain of software."
MARKETING_SUBHEAD = (
    "Dispatch, rates, BOLs, and a cab-ready driver view for owner-operators "
    "and small fleets who live on loaded miles — not empty ones."
)

DRIVERS: tuple[str, ...] = ("Phillip", "Lawson")
OWNERS: tuple[str, ...] = DRIVERS  # operator roles for this tenant
DEFAULT_OWNER = "Phillip"
TRUCK_LABEL = "L&P End-Dump"
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