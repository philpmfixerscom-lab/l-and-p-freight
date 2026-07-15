"""
Rule-based AI engines for L & P Dispatch v3.0 Freight OS.

Transparent scoring, OCR simulation, voice summary, geofence logic, bulk import,
SMS helpers, and PDF generators — no black-box ML.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
import uuid
from contextlib import closing
from datetime import date, datetime
from typing import Any

import pandas as pd

from lp_helpers.database import (
    APP_VERSION,
    ATTACHMENTS_DIR,
    BASE_DIR,
    COMMODITY_OPTIONS,
    PRIMARY_LANE,
    SEED_LEADS,
    TRAILER_MAX_TONS,
    TRAILER_PROFILE,
    clear_cache,
    fetch_loads,
    generate_bol_number,
    get_conn,
    get_setting,
)

GEOFENCE_APPROACH_MULTIPLIER = 2.0

BULK_IMPORT_REQUIRED = [
    "shipper",
    "commodity",
    "weight_tons",
    "miles",
    "pickup_date",
    "destination",
]

# ---------------------------------------------------------------------------
# Geofence / Haversine
# ---------------------------------------------------------------------------


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two WGS84 points."""
    r = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def geofence_zone_status(distance_m: float, radius_m: float) -> str:
    """Traffic-light zone: green = arrived, amber = approaching, red = outside."""
    if distance_m <= radius_m:
        return "green"
    if distance_m <= radius_m * GEOFENCE_APPROACH_MULTIPLIER:
        return "amber"
    return "red"


def proximity_fill_pct(distance_m: float, radius_m: float) -> float:
    """Proximity bar fill — 100% at center, 0% at 2× radius."""
    max_range = max(radius_m * GEOFENCE_APPROACH_MULTIPLIER, 1.0)
    return max(0.0, min(100.0, (1.0 - distance_m / max_range) * 100.0))


def check_geofence_proximity(
    lat: float, lon: float, geofences_df: pd.DataFrame
) -> list[dict[str, Any]]:
    """Haversine check — all geofences with distance, zone, and inside flag."""
    results: list[dict[str, Any]] = []
    if geofences_df is None or geofences_df.empty:
        return results

    for _, g in geofences_df.iterrows():
        dist = haversine_distance_m(
            lat,
            lon,
            float(g["latitude"]),
            float(g["longitude"]),
        )
        radius = float(g["radius_m"])
        zone = geofence_zone_status(dist, radius)
        geofence_name = str(g.get("name", ""))
        results.append(
            {
                "geofence_name": geofence_name,
                "name": geofence_name,
                "distance_m": round(dist, 1),
                "inside": zone == "green",
                "zone": zone,
                "proximity_pct": round(proximity_fill_pct(dist, radius), 1),
                "miles_away": round(dist / 1609.34, 2),
                "latitude": float(g["latitude"]),
                "longitude": float(g["longitude"]),
                "radius_m": radius,
            }
        )

    zone_order = {"green": 0, "amber": 1, "red": 2}
    return sorted(results, key=lambda x: (zone_order.get(x["zone"], 3), x["distance_m"]))


# ---------------------------------------------------------------------------
# Rate & scoring
# ---------------------------------------------------------------------------


def calculate_rate(
    weight_tons: float,
    miles: float,
    loaded_miles: float | None = None,
    commodity: str = "",
) -> tuple[float, float]:
    """
    Rule-based rate: baseline $/ton adjusted by loaded-mile efficiency.
    Returns (rate_per_ton, total_revenue).
    """
    base = PRIMARY_LANE["baseline_rate_per_ton"]
    lm = loaded_miles if loaded_miles and loaded_miles > 0 else miles
    loaded_share = lm / miles if miles > 0 else 1.0

    if loaded_share >= 0.95:
        multiplier = 1.05
    elif loaded_share >= 0.85:
        multiplier = 1.02
    elif loaded_share < 0.70:
        multiplier = 0.95
    else:
        multiplier = 1.0

    commodity_lower = commodity.lower()
    if any(c in commodity_lower for c in ("feldspar", "mica", "spar", "clay")):
        multiplier *= 1.02
    elif "fertilizer" in commodity_lower:
        multiplier *= 1.03
    elif "lime" in commodity_lower:
        multiplier *= 1.01

    rate = round(base * multiplier, 2)
    revenue = round(rate * weight_tons, 2)
    return rate, revenue


def score_load_intelligence(
    shipper: str,
    commodity: str,
    weight_tons: float,
    miles: float,
    loaded_miles: float | None,
    loads_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """Transparent 0–100 load score — rule-based, fully explainable."""
    lm = loaded_miles if loaded_miles and loaded_miles > 0 else miles
    loaded_share = lm / miles if miles > 0 else 0.0
    rate, revenue = calculate_rate(weight_tons, miles, lm, commodity)
    rev_per_mi = revenue / lm if lm else 0.0
    baseline_rev = PRIMARY_LANE["baseline_rate_per_ton"] * weight_tons
    profit_ratio = revenue / baseline_rev if baseline_rev else 1.0
    prof_score = int(max(0, min(100, 50 + (profit_ratio - 1.0) * 120)))

    dh_score = int(
        max(
            0,
            min(
                100,
                loaded_share * 100 + (10 if loaded_share >= 0.85 else 0),
            ),
        )
    )

    comm_lower = commodity.lower()
    if weight_tons > TRAILER_MAX_TONS:
        fit_score = 0
        fit_detail = (
            f"OVERWEIGHT — {weight_tons}t exceeds {TRAILER_MAX_TONS}t limit."
        )
    elif any(
        c in comm_lower
        for c in ("feldspar", "mica", "spar", "clay", "aggregate", "sand", "gravel")
    ):
        fit_score = 98
        fit_detail = f"Lined end-dump ideal for {commodity}."
    elif "fertilizer" in comm_lower or "lime" in comm_lower:
        fit_score = 90
        fit_detail = f"{commodity} — compatible with lined trailer + tarp policy."
    else:
        fit_score = 65
        fit_detail = f"Verify {commodity} compatibility with 39ft lined end-dump."

    hist_score = 70
    hist_detail = "No prior loads for this shipper — neutral historical score."
    if (
        loads_df is not None
        and not loads_df.empty
        and shipper
        and "shipper" in loads_df.columns
    ):
        prior = loads_df[
            loads_df["shipper"].astype(str).str.lower() == shipper.lower()
        ]
        if not prior.empty:
            avg_rev = float(prior["total_revenue"].fillna(0).mean())
            hist_score = int(
                max(
                    40,
                    min(
                        100,
                        60 + (avg_rev / max(baseline_rev, 1) - 1) * 80,
                    ),
                )
            )
            hist_detail = (
                f"{len(prior)} prior load(s) · avg ${avg_rev:,.0f} revenue."
            )

    weights = {
        "profitability": 0.3,
        "deadhead": 0.3,
        "trailer_fit": 0.25,
        "historical": 0.15,
    }
    breakdown = {
        "profitability": {
            "score": prof_score,
            "weight": "30%",
            "detail": (
                f"${rev_per_mi:.2f}/loaded mi · ${revenue:,.0f} total vs "
                f"${baseline_rev:,.0f} baseline."
            ),
        },
        "deadhead": {
            "score": dh_score,
            "weight": "30%",
            "detail": (
                f"Loaded share {loaded_share:.0%} · deadhead "
                f"{max(0, miles - lm):.0f} mi."
            ),
        },
        "trailer_fit": {
            "score": fit_score,
            "weight": "25%",
            "detail": fit_detail,
        },
        "historical": {
            "score": hist_score,
            "weight": "15%",
            "detail": hist_detail,
        },
    }

    total = sum(breakdown[k]["score"] * weights[k] for k in breakdown)
    score = int(round(total))

    deadhead_saved = (
        max(0, (0.75 - loaded_share) * miles) if loaded_share < 0.75 else 0
    )

    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"
    else:
        grade = "D"

    if score >= 75:
        recommendation = "BOOK"
    elif score >= 55:
        recommendation = "NEGOTIATE"
    else:
        recommendation = "PASS"

    if deadhead_saved > 0:
        roi_message = (
            f"This load scores {score}/100 — est. saves {deadhead_saved:.0f} "
            "deadhead mi vs 75% target."
        )
    else:
        roi_message = (
            f"Strong {loaded_share:.0%} loaded share — on-mission for L & P Dispatch."
        )

    return {
        "score": score,
        "grade": grade,
        "recommendation": recommendation,
        "breakdown": breakdown,
        "revenue": revenue,
        "rate_per_ton": rate,
        "roi_message": roi_message,
    }


def simulate_rate_profit(
    weight_tons: float,
    miles: float,
    loaded_miles: float,
    commodity: str,
    rate_override: float | None = None,
) -> dict[str, Any]:
    rate, revenue = calculate_rate(weight_tons, miles, loaded_miles, commodity)
    if rate_override and rate_override > 0:
        rate = rate_override
        revenue = round(rate * weight_tons, 2)
    fuel_est = round(miles * 0.42, 2)
    margin = round(revenue - fuel_est, 2)
    margin_pct = margin / revenue if revenue else 0.0
    per_mile = revenue / loaded_miles if loaded_miles else 0.0
    return {
        "rate_per_ton": rate,
        "revenue": revenue,
        "fuel_est": fuel_est,
        "margin_est": margin,
        "margin_pct": margin_pct,
        "per_mile": per_mile,
    }


# ---------------------------------------------------------------------------
# Document OCR (placeholder)
# ---------------------------------------------------------------------------


def simulate_document_ocr(
    filename: str, hint_text: str = "", demo_pick: int = 0
) -> dict[str, Any]:
    """
    Placeholder OCR — rule-based extraction for offline demo.
    Real OCR can replace this function later (Tesseract / cloud API).
    """
    templates = [
        {
            "shipper": "Sibelco",
            "commodity": "Feldspar",
            "weight_tons": 24.0,
            "miles": 285,
            "loaded_miles": 285,
            "destination": "Kohler area, GA",
            "confidence": 0.94,
            "doc_type": "Scale Ticket",
        },
        {
            "shipper": "Covia",
            "commodity": "Clay",
            "weight_tons": 22.5,
            "miles": 290,
            "loaded_miles": 285,
            "destination": PRIMARY_LANE["destination"],
            "confidence": 0.91,
            "doc_type": "BOL",
        },
        {
            "shipper": "K-T Feldspar",
            "commodity": "Mica",
            "weight_tons": 23.0,
            "miles": 280,
            "loaded_miles": 280,
            "destination": "Central Georgia",
            "confidence": 0.89,
            "doc_type": "Scale Ticket",
        },
    ]
    blob = f"{filename} {hint_text}".lower()

    for lead in SEED_LEADS:
        if lead["company"].lower() in blob:
            t = templates[demo_pick % len(templates)].copy()
            t["shipper"] = lead["company"]
            t["confidence"] = 0.88
            return t

    for c in COMMODITY_OPTIONS:
        if c.lower() in blob:
            t = templates[demo_pick % len(templates)].copy()
            t["commodity"] = c
            return t

    wt = re.search(r"(\d{1,2}(?:\.\d)?)\s*(?:ton|t\b)", blob)
    t = templates[demo_pick % len(templates)].copy()
    if wt:
        t["weight_tons"] = min(float(wt.group(1)), TRAILER_MAX_TONS)
    return t


# ---------------------------------------------------------------------------
# Voice / AI summary
# ---------------------------------------------------------------------------


def summarize_voice_with_ai(text: str, context: str = "dispatch") -> dict[str, Any]:
    """Rule-based voice/text → structured summary + suggested actions."""
    text_l = text.lower()
    actions: list[str] = []
    fields: dict[str, Any] = {}

    for lead in SEED_LEADS:
        if lead["company"].lower() in text_l:
            fields["shipper"] = lead["company"]
            actions.append(
                f"Call back {lead['company']} at {lead['phone']}"
            )

    for c in COMMODITY_OPTIONS:
        if c.lower() in text_l:
            fields["commodity"] = c

    if re.search(r"\b(24|23|22|21|20)\s*(ton|t)?", text_l):
        m = re.search(r"\b(\d{1,2}(?:\.\d)?)\s*(?:ton|t)?", text_l)
        if m:
            fields["weight_tons"] = m.group(1) + "t"

    if "kohler" in text_l or "georgia" in text_l or " ga" in text_l:
        fields["destination"] = PRIMARY_LANE["destination"]

    if "rate" in text_l or "$" in text:
        fields["rate_discussed"] = "Yes — confirm per-ton rate in Load Logger"
        actions.append("Run rate simulator on AI Intelligence tab")

    if "load" in text_l and "no load" not in text_l:
        actions.append("Log load in Load Logger if rate accepted")

    if "callback" in text_l or "call back" in text_l:
        actions.append("Schedule follow-up call in Leads & Calls")

    if not actions:
        actions.append("Review voice memo and log key details in Load Logger")

    summary = (
        f"{context.title()} note captured. "
        + (
            f"Shipper: {fields.get('shipper', 'not detected')}. "
            if fields
            else ""
        )
        + (
            f"Commodity: {fields.get('commodity', 'not detected')}. "
            if "commodity" in fields
            else ""
        )
        + "Owner makes final decision — L & P Dispatch."
    )

    return {
        "summary": summary,
        "fields": fields,
        "suggested_actions": actions[:4],
        "actions": actions[:4],
    }


def smart_arrival_prefill(
    geofence_name: str, load_id: int | None = None
) -> dict[str, str]:
    """Advanced geofence — suggest status + notes on arrival."""
    name_l = geofence_name.lower()
    is_yard = "yard" in name_l or "spruce" in name_l
    is_delivery = "kohler" in name_l or "delivery" in name_l

    load_ref = ""
    shipper = ""
    if load_id:
        loads_df = fetch_loads()
        if not loads_df.empty and "id" in loads_df.columns:
            match = loads_df[loads_df["id"] == load_id]
            if not match.empty:
                row = match.iloc[0]
                load_ref = str(row.get("bol_number", ""))
                shipper = str(row.get("shipper", ""))

    if is_yard:
        return {
            "status": "At Yard",
            "notes": (
                f"Arrived Spruce Pine yard · pre-trip complete · load "
                f"{load_ref or 'unlinked'}."
            ),
            "sms_draft": (
                f"L & P Dispatch: At yard, departing for "
                f"{PRIMARY_LANE['destination']}."
            ),
        }

    if is_delivery:
        return {
            "status": "Delivered",
            "notes": (
                f"Arrived delivery zone · {shipper or 'shipper'} · BOL "
                f"{load_ref or 'TBD'} · on site."
            ),
            "sms_draft": (
                f"L & P Dispatch: Arrived delivery — "
                f"{shipper or 'consignee'}. Ready to dump."
            ),
        }

    return {
        "status": "On Site",
        "notes": (
            f"Geofence arrival: {geofence_name} · load "
            f"{load_ref or 'unlinked'}."
        ),
        "sms_draft": f"L & P Dispatch: On site at {geofence_name}.",
    }


# ---------------------------------------------------------------------------
# Predictive insights & AI suggestions
# ---------------------------------------------------------------------------


def _traffic_to_priority(traffic: str) -> str:
    return {"green": "Low", "amber": "Medium", "red": "High"}.get(traffic, "Medium")


def generate_predictive_insights(
    loads_df: pd.DataFrame, maint_df: pd.DataFrame
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []

    if not loads_df.empty:
        total_m = float(loads_df["miles"].fillna(0).sum())
        loaded = float(
            loads_df["loaded_miles"]
            .fillna(loads_df["miles"])
            .fillna(0)
            .sum()
        )
        share = loaded / total_m if total_m else 0.0
        rev = float(loads_df["total_revenue"].fillna(0).sum())

        if share >= 0.8:
            traffic = "green"
        elif share >= 0.65:
            traffic = "amber"
        else:
            traffic = "red"

        insights.append(
            {
                "category": "Lane Performance",
                "title": f"Primary lane loaded share: {share:.0%}",
                "detail": (
                    f"${rev:,.0f} revenue across {len(loads_df)} loads. "
                    "Target ≥80% loaded miles."
                ),
                "priority": _traffic_to_priority(traffic),
            }
        )

        if "shipper" in loads_df.columns and "total_revenue" in loads_df.columns:
            by_shipper = loads_df.groupby("shipper")["total_revenue"].sum()
            if not by_shipper.empty:
                top_shipper = str(by_shipper.idxmax())
                insights.append(
                    {
                        "category": "Shipper Trend",
                        "title": f"Top shipper: {top_shipper}",
                        "detail": (
                            "Prioritize callbacks when lane is quiet — "
                            "highest historical revenue."
                        ),
                        "priority": "Low",
                    }
                )

    if maint_df is not None and not maint_df.empty:
        upcoming = maint_df[maint_df["status"] != "Completed"]
        for _, row in upcoming.head(3).iterrows():
            due = str(row.get("due_date", ""))
            insights.append(
                {
                    "category": "Maintenance Prediction",
                    "title": f"{row.get('asset', 'Asset')}: {row.get('task', 'Task')}",
                    "detail": (
                        f"Due {due} — schedule before next Kohler run "
                        "to avoid downtime."
                    ),
                    "priority": "Medium",
                }
            )

    insights.append(
        {
            "category": "Backhaul Suggestion",
            "title": "Trimac return lane opportunity",
            "detail": (
                "Call Trimac 828-765-7491 for Central GA → NC backhaul — "
                "saves ~40 deadhead mi."
            ),
            "priority": "Low",
        }
    )
    return insights


def run_ai_suggestion_engine(
    loads_df: pd.DataFrame, leads_df: pd.DataFrame
) -> list[dict[str, str]]:
    """Rule-based suggestions — no ML, fully explainable."""
    suggestions: list[dict[str, str]] = []

    if loads_df.empty:
        suggestions.append(
            {
                "category": "Ops",
                "title": "Log your first load",
                "detail": (
                    "No loads recorded yet. Log a Spruce Pine → Kohler run "
                    "to unlock loaded-mile analytics."
                ),
                "priority": "High",
            }
        )
    else:
        total_miles = float(loads_df["miles"].fillna(0).sum())
        loaded_miles = float(
            loads_df["loaded_miles"]
            .fillna(loads_df["miles"])
            .fillna(0)
            .sum()
        )
        loaded_share = loaded_miles / total_miles if total_miles else 0.0

        if loaded_share < 0.8:
            suggestions.append(
                {
                    "category": "Deadhead",
                    "title": f"Loaded share {loaded_share:.0%} — below 80% target",
                    "detail": (
                        "Mission: minimize deadhead. Consider backhauls from "
                        "Central GA or coordinate with Trimac (828-765-7491) "
                        "for return loads."
                    ),
                    "priority": "High",
                }
            )
        else:
            suggestions.append(
                {
                    "category": "Loaded Miles",
                    "title": f"Loaded share {loaded_share:.0%} — on target",
                    "detail": (
                        "Keep prioritizing Kohler-area deliveries with "
                        "Spruce Pine pickups."
                    ),
                    "priority": "Low",
                }
            )

        if "weight_tons" in loads_df.columns:
            overweight = loads_df[loads_df["weight_tons"] > TRAILER_MAX_TONS]
            if not overweight.empty:
                suggestions.append(
                    {
                        "category": "Weight",
                        "title": (
                            f"{len(overweight)} load(s) exceed "
                            f"{TRAILER_MAX_TONS}t limit"
                        ),
                        "detail": (
                            "39ft lined end-dump rated ~24 tons. "
                            "Reduce weight or split loads."
                        ),
                        "priority": "Critical",
                    }
                )

        if "commodity" in loads_df.columns:
            approved = {c.lower() for c in COMMODITY_OPTIONS[:-1]}
            for commodity in loads_df["commodity"].dropna().unique():
                c_lower = str(commodity).lower()
                if c_lower not in approved:
                    suggestions.append(
                        {
                            "category": "Commodity Fit",
                            "title": f"Non-standard commodity: {commodity}",
                            "detail": (
                                f"Verify {commodity} is compatible with lined "
                                "end-dump and tarp policy. Standard: feldspar, "
                                "mica, spar, clay, rock, lime, fertilizer."
                            ),
                            "priority": "Medium",
                        }
                    )

    suggestions.append(
        {
            "category": "Rate Model",
            "title": (
                f"Baseline ${PRIMARY_LANE['baseline_rate_per_ton']:.2f}/ton — "
                f"{PRIMARY_LANE['origin']} → {PRIMARY_LANE['destination']}"
            ),
            "detail": (
                "Loaded-mile bonus: +5% at ≥95% loaded share, +2% at ≥85%. "
                "Feldspar/mica/spar/clay +2%, fertilizer +3%. "
                f"Trailer max {TRAILER_MAX_TONS}t."
            ),
            "priority": "Info",
        }
    )

    if (
        leads_df is not None
        and not leads_df.empty
        and "status" in leads_df.columns
    ):
        hot = leads_df[leads_df["status"].isin(["New", "Hot", "Active"])]
        if not hot.empty:
            suggestions.append(
                {
                    "category": "Leads",
                    "title": "Call hot leads if lane is quiet",
                    "detail": (
                        "Sibelco 828-592-2780 · Covia 1-800-243-9004 · "
                        "K-T Feldspar 828-765-9621 · Trimac 828-765-7491"
                    ),
                    "priority": "Medium",
                }
            )

    return suggestions


def persist_ai_suggestions(suggestions: list[dict[str, str]]) -> None:
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM ai_suggestions WHERE dismissed = 0")
        for s in suggestions:
            conn.execute(
                "INSERT INTO ai_suggestions (category, title, detail, priority) "
                "VALUES (?,?,?,?)",
                (s["category"], s["title"], s["detail"], s["priority"]),
            )
        conn.commit()
    clear_cache()


# ---------------------------------------------------------------------------
# Dashboard metrics
# ---------------------------------------------------------------------------


def dashboard_metrics(loads_df: pd.DataFrame) -> dict[str, Any]:
    empty = {
        "loads": 0,
        "revenue": 0.0,
        "miles": 0.0,
        "loaded_share": 0.0,
        "avg_rate": 0.0,
        "revenue_per_loaded_mile": 0.0,
        "deadhead_pct": 0.0,
        "deadhead_miles": 0.0,
    }
    if loads_df.empty:
        return empty

    total_miles = float(loads_df["miles"].fillna(0).sum())
    loaded = float(
        loads_df["loaded_miles"].fillna(loads_df["miles"]).fillna(0).sum()
    )
    deadhead = float(loads_df["deadhead_miles"].fillna(0).sum())
    if deadhead <= 0 and total_miles > 0:
        deadhead = max(0.0, total_miles - loaded)
    revenue = float(loads_df["total_revenue"].fillna(0).sum())

    return {
        "loads": len(loads_df),
        "revenue": revenue,
        "miles": total_miles,
        "loaded_share": loaded / total_miles if total_miles else 0.0,
        "avg_rate": float(loads_df["rate_per_ton"].fillna(0).mean()),
        "revenue_per_loaded_mile": revenue / loaded if loaded else 0.0,
        "deadhead_pct": deadhead / total_miles if total_miles else 0.0,
        "deadhead_miles": deadhead,
    }


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------


def normalize_commodity(raw: str) -> tuple[str, bool]:
    """Map import commodity to L & P options. Returns (commodity, was_normalized)."""
    cleaned = str(raw).strip()
    if not cleaned:
        return cleaned, False
    for opt in COMMODITY_OPTIONS:
        if cleaned.lower() == opt.lower():
            return opt, cleaned != opt
    return cleaned, False


def normalize_import_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names, drop blank rows, coerce types for preview."""
    out = df.copy()
    out.columns = [
        str(c).strip().lower().replace(" ", "_") for c in out.columns
    ]
    if out.empty:
        return out

    present = [c for c in BULK_IMPORT_REQUIRED if c in out.columns]
    if not present:
        return out.reset_index(drop=True)

    cleaned = out[present].astype(str).apply(lambda s: s.str.strip())
    cleaned = cleaned.replace({"nan": "", "None": "", "<NA>": ""})
    keep = cleaned.ne("").any(axis=1)
    return out.loc[keep].reset_index(drop=True)


def parse_uploaded_load_file(uploaded: Any) -> pd.DataFrame:
    if str(uploaded.name).lower().endswith(".xlsx"):
        return pd.read_excel(uploaded)
    return pd.read_csv(uploaded)


def bulk_import_template_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "shipper": "Sibelco",
                "commodity": "Feldspar",
                "weight_tons": 24,
                "miles": 285,
                "loaded_miles": 285,
                "pickup_date": str(date.today()),
                "destination": "Kohler area, GA",
                "notes": "Sample row — delete before import",
            },
            {
                "shipper": "Covia",
                "commodity": "Clay",
                "weight_tons": 22,
                "miles": 290,
                "loaded_miles": 285,
                "pickup_date": str(date.today()),
                "destination": PRIMARY_LANE["destination"],
                "notes": "Deadhead example — 5 mi empty",
            },
        ]
    )


def build_bulk_template_xlsx() -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        bulk_import_template_df().to_excel(
            writer, index=False, sheet_name="loads"
        )
    buffer.seek(0)
    return buffer.read()


def validate_bulk_row(
    row: dict[str, Any], row_num: int
) -> tuple[bool, str, dict[str, Any] | None]:
    """Validate a single import row. Returns (ok, message, cleaned_row)."""
    errors: list[str] = []
    warnings: list[str] = []

    shipper = str(row.get("shipper", "")).strip()
    commodity_raw = str(row.get("commodity", "")).strip()
    destination = str(row.get("destination", "")).strip()

    if not shipper:
        errors.append("missing shipper")
    if not commodity_raw:
        errors.append("missing commodity")

    commodity, norm = normalize_commodity(commodity_raw)
    if norm:
        warnings.append(f"commodity normalized to '{commodity}'")

    try:
        weight = float(row.get("weight_tons", 0))
    except (TypeError, ValueError):
        errors.append("invalid weight_tons")
        weight = 0.0

    if weight <= 0:
        errors.append("weight must be > 0")
    elif weight > TRAILER_MAX_TONS:
        errors.append(
            f"weight {weight}t exceeds {TRAILER_MAX_TONS}t trailer limit"
        )

    try:
        miles = float(row.get("miles", 0))
    except (TypeError, ValueError):
        errors.append("invalid miles")
        miles = 0.0

    if miles <= 0:
        errors.append("miles must be > 0")

    loaded_raw = row.get("loaded_miles")
    loaded_miles: float | None = None
    if loaded_raw is not None and str(loaded_raw).strip().lower() not in (
        "",
        "nan",
        "none",
    ):
        try:
            loaded_miles = float(loaded_raw)
            if loaded_miles < 0:
                errors.append("loaded_miles cannot be negative")
            elif miles > 0 and loaded_miles > miles:
                warnings.append(
                    f"loaded_miles {loaded_miles} > miles {miles} — capped to miles"
                )
                loaded_miles = miles
        except (TypeError, ValueError):
            warnings.append("invalid loaded_miles — using miles")

    pickup_raw = row.get("pickup_date")
    pickup_date = str(date.today())
    if pickup_raw is not None and str(pickup_raw).strip().lower() not in (
        "",
        "nan",
        "none",
    ):
        try:
            pickup_date = pd.to_datetime(pickup_raw).strftime("%Y-%m-%d")
        except Exception:
            warnings.append("could not parse pickup_date — using today")

    if not destination:
        destination = PRIMARY_LANE["destination"]
        warnings.append("missing destination — using primary lane default")

    notes = str(row.get("notes", "")).strip()
    if notes.lower() in ("nan", "none"):
        notes = ""

    approved = {c.lower() for c in COMMODITY_OPTIONS[:-1]}
    if commodity and commodity.lower() not in approved:
        warnings.append(
            f"non-standard commodity '{commodity}' — verify trailer fit"
        )

    if errors:
        return (
            False,
            f"Row {row_num}: FAIL — {'; '.join(errors)}",
            None,
        )

    rate, revenue = calculate_rate(weight, miles, loaded_miles, commodity)
    deadhead = max(
        0.0,
        miles - (loaded_miles if loaded_miles is not None else miles),
    )
    warn_suffix = f" | WARN: {'; '.join(warnings)}" if warnings else ""
    cleaned = {
        "bol_number": generate_bol_number(),
        "shipper": shipper,
        "commodity": commodity,
        "weight_tons": weight,
        "miles": miles,
        "loaded_miles": loaded_miles if loaded_miles is not None else miles,
        "deadhead_miles": deadhead,
        "pickup_date": pickup_date,
        "origin": PRIMARY_LANE["origin"],
        "destination": destination,
        "rate_per_ton": rate,
        "total_revenue": revenue,
        "notes": notes + warn_suffix,
        "status": "Imported",
    }
    status = "WARN" if warnings else "OK"
    msg = f"Row {row_num}: {status}"
    if warnings:
        msg += f" — {'; '.join(warnings)}"
    return True, msg, cleaned


def validate_bulk_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    preview_rows: list[dict[str, Any]] = []
    valid_rows: list[dict[str, Any]] = []
    ok_count = warn_count = fail_count = 0

    for i, row in df.iterrows():
        row_num = int(i) + 2
        ok, msg, cleaned = validate_bulk_row(row.to_dict(), row_num)
        status = "FAIL"
        if ok:
            status = "WARN" if "WARN" in msg else "OK"
            if cleaned:
                valid_rows.append(cleaned)
            if status == "WARN":
                warn_count += 1
            else:
                ok_count += 1
        else:
            fail_count += 1

        preview_rows.append(
            {
                "row": row_num,
                "status": status,
                "shipper": row.get("shipper", ""),
                "commodity": row.get("commodity", ""),
                "weight_tons": row.get("weight_tons", ""),
                "miles": row.get("miles", ""),
                "message": msg,
            }
        )

    total_revenue = sum(r["total_revenue"] for r in valid_rows)
    return {
        "preview_df": pd.DataFrame(preview_rows),
        "valid_rows": valid_rows,
        "ok_count": ok_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "total_rows": len(df),
        "total_revenue": total_revenue,
        "messages": [p["message"] for p in preview_rows],
    }


def bulk_insert_loads(rows: list[dict[str, Any]]) -> int:
    with closing(get_conn()) as conn:
        for r in rows:
            conn.execute(
                """
                INSERT INTO loads (bol_number, shipper, commodity, weight_tons, miles,
                   loaded_miles, deadhead_miles, pickup_date, origin, destination,
                   rate_per_ton, total_revenue, status, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    r["bol_number"],
                    r["shipper"],
                    r["commodity"],
                    r["weight_tons"],
                    r["miles"],
                    r["loaded_miles"],
                    r["deadhead_miles"],
                    r["pickup_date"],
                    r["origin"],
                    r["destination"],
                    r["rate_per_ton"],
                    r["total_revenue"],
                    r["status"],
                    r["notes"],
                ),
            )
        conn.commit()
    clear_cache()
    return len(rows)


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------


def generate_sms_text(
    lead: dict[str, Any], alert_type: str, extra: str = ""
) -> str:
    company = lead.get("company", "Contact")
    if alert_type == "arrival":
        return (
            f"L & P Dispatch: Arrived at {extra}. {company} — Phillip, "
            "39ft end-dump. Reply STOP to opt out."
        )
    if alert_type == "load update":
        return (
            f"L & P Dispatch: Load update for {company} — {extra} — "
            "Spruce Pine NC. Reply STOP to opt out."
        )
    if alert_type == "departure":
        return (
            f"L & P Dispatch: Departing {extra} — {company} — "
            "Phillip / Lawson. Reply STOP to opt out."
        )
    return (
        f"L & P Dispatch: {extra} — {company} — Phillip / Lawson. "
        "Reply STOP to opt out."
    )


def log_sms(
    lead_id: int | None,
    alert_type: str,
    message: str,
    sent_via: str = "clipboard",
    twilio_sid: str | None = None,
) -> None:
    with closing(get_conn()) as conn:
        conn.execute(
            "INSERT INTO sms_log (lead_id, alert_type, message, sent_via, twilio_sid) "
            "VALUES (?,?,?,?,?)",
            (lead_id, alert_type, message, sent_via, twilio_sid),
        )
        conn.commit()


def send_twilio_sms(to_number: str, body: str) -> str:
    """Send via Twilio. Returns message SID or raises."""
    sid = get_setting("twilio_sid")
    token = get_setting("twilio_token")
    from_num = get_setting("twilio_from")
    if not all([sid, token, from_num]):
        raise ValueError(
            "Twilio credentials incomplete — fill SID, Token, and From number "
            "in Settings."
        )
    try:
        from twilio.rest import Client
    except ImportError as exc:
        raise ImportError(
            "twilio package not installed. Run: pip install twilio"
        ) from exc

    client = Client(sid, token)
    msg = client.messages.create(body=body, from_=from_num, to=to_number)
    return msg.sid


# ---------------------------------------------------------------------------
# Voice recording
# ---------------------------------------------------------------------------


def _audio_bytes_hash(audio_bytes: bytes) -> str:
    return hashlib.sha256(audio_bytes).hexdigest()[:16]


def save_voice_recording(
    audio_bytes: bytes,
    category: str = "dispatch",
    ref_id: int | None = None,
) -> str:
    """Persist voice memo under ./attachments/ — returns path relative to project root."""
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    ref_part = f"_{ref_id}" if ref_id is not None else ""
    fname = (
        f"voice_{category}{ref_part}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:6]}.wav"
    )
    path = ATTACHMENTS_DIR / fname
    path.write_bytes(audio_bytes)
    return str(path.relative_to(BASE_DIR))


def resolve_voice_path(relative_path: str | None) -> Any:
    if not relative_path:
        return None
    full = BASE_DIR / relative_path
    return full if full.exists() else None


def clear_voice_session(key: str) -> None:
    import streamlit as st

    for suffix in ("path", "hash"):
        st.session_state.pop(f"voice_{suffix}_{key}", None)
        st.session_state.pop(f"voice_text_{key}", None)


def merge_voice_notes(text_notes: str, voice_path: str | None) -> str:
    parts: list[str] = []
    if text_notes and text_notes.strip():
        parts.append(text_notes.strip())
    if voice_path:
        parts.append(f"[Voice memo: {voice_path}]")
    return "\n".join(parts)


def render_voice_input_panel(
    key: str,
    category: str,
    ref_id: int | None = None,
    text_label: str = "Type notes",
    text_placeholder: str = "e.g. On site, ready to load feldspar",
    panel_title: str = "🎙️ Voice Input",
    panel_hint: str = "Record or type — saved locally on this machine.",
) -> tuple[str | None, str]:
    """
    Reusable voice + text capture. Returns (voice_relative_path, text_notes).
    Voice deduped by content hash — won't create duplicate files on rerun.
    """
    import streamlit as st

    path_key = f"voice_path_{key}"
    hash_key = f"voice_hash_{key}"

    st.markdown(
        f"""
        <div class="lf-voice-panel">
            <div class="lf-voice-panel-title">{panel_title}</div>
            <div class="lf-voice-panel-hint">{panel_hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    audio = st.audio_input("Record voice memo", key=f"audio_{key}")
    voice_path = st.session_state.get(path_key)

    if audio:
        audio_bytes = audio.getvalue()
        if audio_bytes:
            current_hash = _audio_bytes_hash(audio_bytes)
            if st.session_state.get(hash_key) != current_hash:
                voice_path = save_voice_recording(
                    audio_bytes, category=category, ref_id=ref_id
                )
                st.session_state[path_key] = voice_path
                st.session_state[hash_key] = current_hash
            else:
                voice_path = st.session_state.get(path_key)
            st.success(f"Voice saved locally: {voice_path}")

    saved_file = resolve_voice_path(voice_path)
    if saved_file:
        st.audio(str(saved_file))
        st.caption(f"📁 {voice_path}")

    text_notes = st.text_area(
        text_label,
        placeholder=text_placeholder,
        key=f"voice_text_{key}",
        height=100,
    )
    return voice_path, (text_notes or "").strip()


# ---------------------------------------------------------------------------
# PDF generators
# ---------------------------------------------------------------------------


def generate_bol_pdf(load: dict[str, Any]) -> bytes:
    """Simple branded BOL PDF using fpdf (offline fallback)."""
    try:
        from fpdf import FPDF
    except ImportError:
        from lp_helpers.bol_export import generate_branded_bol_pdf

        return generate_branded_bol_pdf(
            load,
            app_version=APP_VERSION,
            trailer_profile=TRAILER_PROFILE,
            primary_origin=PRIMARY_LANE["origin"],
        )

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "L & P Dispatch", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Bill of Lading - {TRAILER_PROFILE}",
        ln=True,
    )
    pdf.ln(4)

    rows = [
        ("BOL #", str(load.get("bol_number", "-"))),
        ("Date", str(load.get("pickup_date") or date.today())),
        ("Shipper", str(load.get("shipper", "-"))),
        ("Commodity", str(load.get("commodity", "-"))),
        ("Origin", str(load.get("origin", PRIMARY_LANE["origin"]))),
        ("Destination", str(load.get("destination", "-"))),
        ("Weight (tons)", str(load.get("weight_tons", "-"))),
        ("Miles", str(load.get("miles", "-"))),
        ("Loaded Miles", str(load.get("loaded_miles", "-"))),
        ("Rate/Ton", f"${float(load.get('rate_per_ton', 0)):.2f}"),
        ("Total Revenue", f"${float(load.get('total_revenue', 0)):,.2f}"),
        ("Status", str(load.get("status", "Logged"))),
    ]
    pdf.set_font("Helvetica", "", 10)
    for label, value in rows:
        pdf.cell(45, 7, label, border=1)
        pdf.cell(0, 7, value, border=1, ln=True)

    notes = load.get("notes")
    if notes:
        pdf.ln(4)
        pdf.multi_cell(0, 6, f"Notes: {notes}")

    pdf.ln(8)
    pdf.cell(0, 7, "Shipper Signature: _________________________  Date: __________", ln=True)
    pdf.ln(6)
    pdf.cell(0, 7, "Driver Signature: _________________________  Date: __________", ln=True)
    pdf.ln(6)
    pdf.cell(
        0,
        7,
        "Receiver Signature: _______________________  Date: __________",
        ln=True,
    )

    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)


def generate_performance_report_pdf(
    loads_df: pd.DataFrame, metrics: dict[str, Any]
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("L &amp; P DISPATCH — PERFORMANCE REPORT", styles["Heading1"]),
        Paragraph(
            f"Freight OS v{APP_VERSION} · Phillip / Lawson · {date.today()}",
            styles["Normal"],
        ),
        Spacer(1, 0.2 * inch),
        Paragraph(
            f"Loads: {metrics.get('loads', 0)} · Revenue: "
            f"${metrics.get('revenue', 0):,.0f} · Loaded share: "
            f"{metrics.get('loaded_share', 0):.0%}",
            styles["Normal"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if not loads_df.empty:
        rows = [["BOL", "Shipper", "Revenue", "Miles"]]
        for _, r in loads_df.head(15).iterrows():
            rows.append(
                [
                    str(r.get("bol_number", "")),
                    str(r.get("shipper", "")),
                    f"${float(r.get('total_revenue', 0)):,.0f}",
                    str(r.get("miles", "")),
                ]
            )
        t = Table(rows, colWidths=[1.4 * inch, 1.8 * inch, 1.2 * inch, 0.8 * inch])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1628")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, "#f1f5f9"]),
                ]
            )
        )
        story.append(t)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def generate_invoice_preview_pdf(load: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    rev = float(load.get("total_revenue", 0))
    story = [
        Paragraph("L &amp; P DISPATCH — INVOICE PREVIEW", styles["Heading1"]),
        Paragraph(
            "Phillip / Lawson · Spruce Pine NC · 39ft End-Dump",
            styles["Normal"],
        ),
        Spacer(1, 0.2 * inch),
        Paragraph(
            f"<b>Invoice #</b> INV-{load.get('bol_number', 'DRAFT')}",
            styles["Normal"],
        ),
        Paragraph(
            f"<b>Bill To:</b> {load.get('shipper', '—')}",
            styles["Normal"],
        ),
        Paragraph(
            f"<b>Lane:</b> {load.get('origin', PRIMARY_LANE['origin'])} → "
            f"{load.get('destination', '—')}",
            styles["Normal"],
        ),
        Spacer(1, 0.2 * inch),
    ]

    line_data = [
        ["Description", "Qty", "Rate", "Amount"],
        [
            f"{load.get('commodity', 'Haul')} haul · {load.get('weight_tons', 0)}t",
            f"{load.get('weight_tons', 0)} ton",
            f"${float(load.get('rate_per_ton', 0)):.2f}",
            f"${rev:,.2f}",
        ],
        ["TOTAL", "", "", f"${rev:,.2f}"],
    ]
    t = Table(line_data, colWidths=[2.8 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e85d04")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
            ]
        )
    )
    story.append(t)
    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ---------------------------------------------------------------------------
# IFTA
# ---------------------------------------------------------------------------


def ifta_summary(fuel_df: pd.DataFrame) -> pd.DataFrame:
    if fuel_df is None or fuel_df.empty:
        return pd.DataFrame(columns=["state", "gallons", "cost", "fills"])
    df = fuel_df.copy()
    if "state" not in df.columns:
        df["state"] = "UNK"
    agg: dict[str, tuple[str, str]] = {
        "gallons": ("gallons", "sum"),
        "cost": ("cost", "sum"),
    }
    if "id" in df.columns:
        agg["fills"] = ("id", "count")
    else:
        agg["fills"] = ("gallons", "count")
    return (
        df.groupby("state", as_index=False)
        .agg(**agg)
        .sort_values("gallons", ascending=False)
    )