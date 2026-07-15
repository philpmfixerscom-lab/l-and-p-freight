"""Deadhead minimization — practical return-load scoring for bulk haulers.

Scenario: just delivered in Central Georgia; need a load that reduces empty
miles back toward Spruce Pine / western NC. Transparent rules only (no ML).

Scoring is broken into four buckets a driver/dispatcher can understand:
  1. Pickup proximity (can I load near where I am?)
  2. Homebound direction (does the drop pull me north toward home?)
  3. End-dump commodity fit
  4. Rate quality vs lane baseline ($/ton context for bulk)

v1 limitations: keyword geography (not true lat/lon routing), no live board
API, no historical win-rate. See module docstring bottom / score_return_load.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_HOME = "Spruce Pine, NC"
DEFAULT_DELIVERY_ZONE = "Central Georgia (Kohler area)"
DEFAULT_LANE_BASELINE_PER_TON = 48.0  # typical SP→GA bulk anchor

# --- Geography keyword rings (practical, not GIS) ---

# Where the truck is now after a Kohler-area drop
GA_CORE: tuple[str, ...] = (
    "kohler",
    "central georgia",
    "central ga",
    "macon",
    "milledgeville",
    "warner robins",
    "dublin",
    "sandersville",
    "augusta",
    "athens",
    "griffin",
)
GA_WIDE: tuple[str, ...] = (
    "georgia",
    " ga",
    "ga ",
    "atlanta",
    "columbus",
    "savannah",
    "albany",
    "valdosta",
)
SC_NEAR: tuple[str, ...] = (
    "south carolina",
    " sc",
    "sc ",
    "greenville",
    "spartanburg",
    "anderson",
    "columbia sc",
)

# Direction toward home: tighter = better for deadhead reduction
HOME_CORE: tuple[str, ...] = (
    "spruce pine",
    "mitchell",
    "burnsville",
    "bakersville",
    "marion nc",
    "mcdowell",
    "avery",
    "yancey",
)
HOME_CORRIDOR: tuple[str, ...] = (
    "asheville",
    "hickory",
    "lenoir",
    "morganton",
    "boone",
    "i-26",
    "i26",
    "hwy 19e",
    "19e",
    "hwy 226",
    "highway 226",
    "western nc",
    "west nc",
    "mtn city",
)
HOME_STATE: tuple[str, ...] = (
    "north carolina",
    " n.c",
    " nc",
    "nc ",
    ", nc",
)
HOME_NEAR_STATES: tuple[str, ...] = (
    "tennessee",
    " tn",
    "johnson city",
    "kingsport",
    "bristol",
    "southwest va",
    "virginia",
)

SOUTH_AWAY: tuple[str, ...] = (
    "florida",
    " fl",
    "miami",
    "tampa",
    "orlando",
    "jacksonville fl",
    "south florida",
    "mobile al",
    "birmingham",  # west, not home
    "new orleans",
    "louisiana",
)

# End-dump fit tiers
DUMP_EXCELLENT: tuple[str, ...] = (
    "feldspar",
    "mica",
    "quartz",
    "spar",
    "clay",
    "sand",
    "gravel",
    "aggregate",
    "crushed",
    "stone",
    "rock",
    "lime",
    "ash",
    "dirt",
    "fill",
    "slag",
)
DUMP_OK: tuple[str, ...] = (
    "fertilizer",
    "mulch",
    "bulk",
    "grain",  # possible but messy
    "salt",
    "coal",
)
DUMP_BAD: tuple[str, ...] = (
    "reefer",
    "produce",
    "pallet",
    "van only",
    "dry van",
    "flatbed steel",
    "lumber package",
    "hazmat liquid",
    "tanker",
    "container",
)


@dataclass
class DeadheadScore:
    """Transparent score for a return-load candidate."""

    score: int  # 0-100 overall
    grade: str  # A/B/C/D
    label: str
    reasons: list[str]
    # Bucket breakdown so UI can show "why" at a glance
    proximity_pts: int = 0  # max 25
    direction_pts: int = 0  # max 35
    commodity_pts: int = 0  # max 20
    rate_pts: int = 0  # max 20
    empty_miles_estimate: float | None = None
    source: str = "rules_v2"
    extras: dict[str, Any] = field(default_factory=dict)


def _blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def _hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for k in keywords if k in text)


def _parse_rate(rate_hint: str | float | None) -> tuple[float | None, str]:
    """Return (numeric_value, kind) where kind is 'per_ton' | 'per_mile' | 'total' | 'unknown'."""
    if rate_hint is None or rate_hint == "":
        return None, "unknown"
    if isinstance(rate_hint, (int, float)):
        v = float(rate_hint)
        # Heuristic: < 15 likely $/mi; 15-120 likely $/ton; else total $
        if v < 15:
            return v, "per_mile"
        if v <= 120:
            return v, "per_ton"
        return v, "total"
    s = str(rate_hint).lower().replace(",", "")
    kind = "unknown"
    if "/ton" in s or "per ton" in s or "ton" in s:
        kind = "per_ton"
    elif "/mi" in s or "per mile" in s or "rpm" in s:
        kind = "per_mile"
    elif "total" in s or "$" in s and s.count(".") <= 1:
        kind = "total"
    digits = "".join(c if (c.isdigit() or c == ".") else " " for c in s)
    parts = [p for p in digits.split() if p]
    if not parts:
        return None, kind
    try:
        v = float(parts[0])
    except ValueError:
        return None, kind
    if kind == "unknown":
        if v < 15:
            kind = "per_mile"
        elif v <= 120:
            kind = "per_ton"
        else:
            kind = "total"
    return v, kind


def grade_from_score(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def score_return_load(
    *,
    origin: str = "",
    destination: str = "",
    commodity: str = "",
    rate_hint: str | float | None = None,
    notes: str = "",
    home: str = DEFAULT_HOME,
    current_location: str = DEFAULT_DELIVERY_ZONE,
    empty_miles_estimate: float | None = None,
    lane_baseline_per_ton: float = DEFAULT_LANE_BASELINE_PER_TON,
) -> DeadheadScore:
    """Score a GA-area → homebound candidate with four explainable buckets.

    Practical framing for the user:
      "Would this load beat running empty from Central GA back to Spruce Pine?"
    """
    reasons: list[str] = []
    o = _blob(origin)
    d = _blob(destination)
    c = _blob(commodity)
    n = _blob(notes)
    cur = _blob(current_location)
    all_txt = _blob(origin, destination, commodity, notes, rate_hint)

    # ---- 1) Pickup proximity (0-25): near the truck after delivery ----
    proximity = 0
    if _hits(o, GA_CORE) or _hits(o, GA_CORE) == 0 and _hits(cur + " " + o, GA_CORE):
        if _hits(o, GA_CORE):
            proximity = 25
            reasons.append("Pickup in Core GA delivery zone (can load soon)")
        elif _hits(o, GA_WIDE):
            proximity = 18
            reasons.append("Pickup in Georgia — short empty to shipper")
    elif _hits(o, GA_WIDE):
        proximity = 18
        reasons.append("Pickup in Georgia — short empty to shipper")
    elif _hits(o, SC_NEAR):
        proximity = 14
        reasons.append("Pickup in SC — reasonable empty from GA")
    elif "nc" in o or "north carolina" in o:
        proximity = 6
        reasons.append("Pickup already in NC — may require long empty first")
    else:
        proximity = 4
        reasons.append("Pickup far from GA delivery — factor empty to shipper")

    # slight boost if origin text overlaps current location tokens
    if any(tok in o for tok in cur.replace(",", " ").split() if len(tok) > 3):
        proximity = min(25, proximity + 3)

    # ---- 2) Direction toward home corridor (0-35) ----
    direction = 0
    home_town = home.lower().split(",")[0].strip()
    if home_town and home_town in d:
        direction = 35
        reasons.append(f"Drops at home base ({home_town.title()})")
    elif _hits(d, HOME_CORE):
        direction = 32
        reasons.append("Destination in Spruce Pine / mountain core")
    elif _hits(d, HOME_CORRIDOR):
        direction = 26
        reasons.append("Destination on homebound corridor (I-26 / W NC)")
    elif _hits(d, HOME_STATE) and not _hits(d, SOUTH_AWAY):
        direction = 18
        reasons.append("Destination in North Carolina (partial home pull)")
    elif _hits(d, HOME_NEAR_STATES):
        direction = 12
        reasons.append("Near-home state (TN/VA) — better than southbound")
    else:
        direction = 4
        reasons.append("Destination not homebound — limited deadhead help")

    if _hits(d, SOUTH_AWAY):
        direction = max(0, direction - 18)
        reasons.append("Pulls further south/away — hurts next empty")

    if any(w in all_txt for w in ("backhaul", "return load", "northbound", "head home")):
        direction = min(35, direction + 4)
        reasons.append("Explicit backhaul / northbound intent")

    # ---- 3) End-dump commodity (0-20) ----
    commodity_pts = 0
    if _hits(c, DUMP_EXCELLENT):
        commodity_pts = 20
        reasons.append("Excellent end-dump commodity (bulk mineral/agg)")
    elif _hits(c, DUMP_OK):
        commodity_pts = 12
        reasons.append("Acceptable bulk for end-dump — confirm washout/tarp")
    elif _hits(c, DUMP_BAD):
        commodity_pts = 0
        reasons.append("Poor end-dump fit (van/reefer/tanker-style freight)")
    elif c.strip():
        commodity_pts = 6
        reasons.append("Unknown commodity — verify liner, tarp, gate")
    else:
        commodity_pts = 3
        reasons.append("No commodity listed — verify before booking")

    # ---- 4) Rate quality vs lane (0-20) ----
    rate_pts = 0
    rate_val, rate_kind = _parse_rate(rate_hint)
    if rate_val is None:
        rate_pts = 6
        reasons.append("No rate given — score assumes break-even vs empty")
    elif rate_kind == "per_ton":
        # Relative to baseline bulk lane (~$48/t outbound reference)
        ratio = rate_val / max(lane_baseline_per_ton, 1.0)
        if ratio >= 1.05:
            rate_pts = 20
            reasons.append(f"Rate ${rate_val:g}/t at/above lane baseline (${lane_baseline_per_ton:g})")
        elif ratio >= 0.85:
            rate_pts = 14
            reasons.append(f"Rate ${rate_val:g}/t near baseline — OK for homebound")
        elif ratio >= 0.65:
            rate_pts = 8
            reasons.append(f"Rate ${rate_val:g}/t soft — only if empty otherwise")
        else:
            rate_pts = 2
            reasons.append(f"Rate ${rate_val:g}/t weak vs baseline")
    elif rate_kind == "per_mile":
        if rate_val >= 2.5:
            rate_pts = 16
            reasons.append(f"RPM ${rate_val:g} strong for return")
        elif rate_val >= 1.8:
            rate_pts = 11
            reasons.append(f"RPM ${rate_val:g} acceptable for homebound")
        else:
            rate_pts = 4
            reasons.append(f"RPM ${rate_val:g} low — watch fuel")
    else:  # total $
        if rate_val >= 1200:
            rate_pts = 15
            reasons.append(f"Total ~${rate_val:,.0f} looks workable")
        elif rate_val >= 700:
            rate_pts = 10
            reasons.append(f"Total ~${rate_val:,.0f} — check miles")
        else:
            rate_pts = 4
            reasons.append(f"Total ~${rate_val:,.0f} may not beat empty+time")

    # Optional empty-miles adjustment (if caller estimates)
    if empty_miles_estimate is not None:
        if empty_miles_estimate <= 40:
            proximity = min(25, proximity + 3)
            reasons.append(f"~{empty_miles_estimate:.0f} mi empty to shipper (tight)")
        elif empty_miles_estimate >= 150:
            proximity = max(0, proximity - 6)
            reasons.append(f"~{empty_miles_estimate:.0f} mi empty to shipper (long)")

    raw = proximity + direction + commodity_pts + rate_pts
    score = max(0, min(100, raw))
    grade = grade_from_score(score)

    if grade == "A":
        label = "Book this homebound — beats empty"
    elif grade == "B":
        label = "Solid return — worth the call"
    elif grade == "C":
        label = "Borderline — check miles & wait time"
    else:
        label = "Weak — running empty may be cleaner"

    return DeadheadScore(
        score=score,
        grade=grade,
        label=label,
        reasons=reasons,
        proximity_pts=proximity,
        direction_pts=direction,
        commodity_pts=commodity_pts,
        rate_pts=rate_pts,
        empty_miles_estimate=empty_miles_estimate,
        source="rules_v2",
        extras={
            "rate_value": rate_val,
            "rate_kind": rate_kind,
            "baseline_per_ton": lane_baseline_per_ton,
        },
    )


def rank_return_candidates(
    candidates: list[dict[str, Any]],
    *,
    home: str = DEFAULT_HOME,
    current_location: str = DEFAULT_DELIVERY_ZONE,
    lane_baseline_per_ton: float = DEFAULT_LANE_BASELINE_PER_TON,
) -> list[tuple[dict[str, Any], DeadheadScore]]:
    ranked: list[tuple[dict[str, Any], DeadheadScore]] = []
    for c in candidates:
        sc = score_return_load(
            origin=str(c.get("origin") or ""),
            destination=str(c.get("destination") or c.get("lane") or ""),
            commodity=str(c.get("commodity") or ""),
            rate_hint=c.get("rate") or c.get("rate_per_ton"),
            notes=str(c.get("notes") or c.get("contact") or ""),
            home=home,
            current_location=current_location,
            empty_miles_estimate=c.get("empty_miles_estimate"),
            lane_baseline_per_ton=lane_baseline_per_ton,
        )
        # Prefer parsing lane into origin/dest when only lane present
        if not c.get("origin") and c.get("lane"):
            lane = str(c["lane"])
            if "→" in lane or "->" in lane:
                sep = "→" if "→" in lane else "->"
                left, right = [p.strip() for p in lane.split(sep, 1)]
                sc = score_return_load(
                    origin=left,
                    destination=right,
                    commodity=str(c.get("commodity") or ""),
                    rate_hint=c.get("rate") or c.get("rate_per_ton"),
                    notes=str(c.get("notes") or ""),
                    home=home,
                    current_location=current_location,
                    lane_baseline_per_ton=lane_baseline_per_ton,
                )
        ranked.append((c, sc))
    ranked.sort(key=lambda x: x[1].score, reverse=True)
    return ranked


def opportunities_as_candidates(opportunities_df: Any) -> list[dict[str, Any]]:
    if opportunities_df is None:
        return []
    try:
        if hasattr(opportunities_df, "empty") and opportunities_df.empty:
            return []
        records = opportunities_df.to_dict("records")
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for r in records:
        lane = str(r.get("lane") or "")
        origin, destination = "", lane
        if "→" in lane:
            a, b = [p.strip() for p in lane.split("→", 1)]
            origin, destination = a, b
        elif "->" in lane:
            a, b = [p.strip() for p in lane.split("->", 1)]
            origin, destination = a, b
        out.append(
            {
                "id": r.get("id"),
                "origin": origin,
                "destination": destination,
                "commodity": r.get("commodity"),
                "rate": r.get("rate"),
                "notes": r.get("notes"),
                "contact": r.get("contact"),
                "lane": lane,
                "source": r.get("source") or "board",
            }
        )
    return out


def last_delivery_location(loads_df: Any) -> str | None:
    """Best-effort 'where am I empty' from recent delivered loads."""
    try:
        if loads_df is None or getattr(loads_df, "empty", True):
            return None
        df = loads_df.copy()
        if "status" not in df.columns:
            return None
        delivered = df[df["status"].astype(str).str.lower().isin(["delivered", "complete", "completed"])]
        if delivered.empty:
            # fall back to any load with destination
            use = df
        else:
            use = delivered
        if "pickup_date" in use.columns:
            use = use.sort_values("pickup_date", ascending=False)
        dest = use.iloc[0].get("destination")
        return str(dest) if dest else None
    except Exception:
        return None


def estimate_empty_home_miles(
    current_location: str = DEFAULT_DELIVERY_ZONE,
    home: str = DEFAULT_HOME,
) -> float:
    """Rough empty miles if running home with no backhaul (keyword heuristic)."""
    cur = _blob(current_location)
    # Known lane: Central GA / Kohler ↔ Spruce Pine ~285 loaded; empty similar
    if _hits(cur, GA_CORE) or _hits(cur, GA_WIDE) or "georgia" in cur or "kohler" in cur:
        return 285.0
    if _hits(cur, SC_NEAR):
        return 200.0
    if "nc" in cur or "north carolina" in cur:
        return 80.0
    return 250.0


def estimate_empty_to_pickup(origin: str, current_location: str) -> float:
    """Rough empty miles from current empty spot to candidate pickup."""
    o = _blob(origin)
    cur = _blob(current_location)
    if _hits(o, GA_CORE) and (_hits(cur, GA_CORE) or _hits(cur, GA_WIDE)):
        return 35.0
    if _hits(o, GA_WIDE) and (_hits(cur, GA_CORE) or _hits(cur, GA_WIDE)):
        return 75.0
    if _hits(o, SC_NEAR):
        return 120.0
    if "nc" in o or "north carolina" in o:
        return 220.0
    return 100.0


def estimate_loaded_toward_home(destination: str, home: str = DEFAULT_HOME) -> float:
    """Rough loaded miles on the return leg toward home."""
    d = _blob(destination)
    if home.lower().split(",")[0] in d or _hits(d, HOME_CORE):
        return 280.0
    if _hits(d, HOME_CORRIDOR):
        return 220.0
    if _hits(d, HOME_STATE):
        return 180.0
    if _hits(d, HOME_NEAR_STATES):
        return 150.0
    return 120.0


def estimate_return_benefit(
    score: DeadheadScore,
    *,
    origin: str = "",
    destination: str = "",
    current_location: str = DEFAULT_DELIVERY_ZONE,
    home: str = DEFAULT_HOME,
    weight_tons: float = 24.0,
    fuel_cost_per_mile: float = 0.85,
) -> dict[str, Any]:
    """Dollar/mile style benefit vs running empty all the way home.

    v1 uses corridor heuristics — not GPS routing. Shown as estimates.
    """
    empty_home = estimate_empty_home_miles(current_location, home)
    empty_to_pu = estimate_empty_to_pickup(origin, current_location)
    loaded_mi = estimate_loaded_toward_home(destination, home)

    # Remaining empty after drop if not fully home (simplified)
    remaining_empty = max(0.0, empty_home - loaded_mi * 0.85) if score.direction_pts >= 18 else empty_home * 0.5

    pure_empty_cost = empty_home * fuel_cost_per_mile
    with_load_empty_cost = (empty_to_pu + remaining_empty) * fuel_cost_per_mile

    rate_val = score.extras.get("rate_value")
    rate_kind = score.extras.get("rate_kind") or "unknown"
    revenue = 0.0
    if rate_val is not None:
        if rate_kind == "per_ton":
            revenue = float(rate_val) * weight_tons
        elif rate_kind == "per_mile":
            revenue = float(rate_val) * loaded_mi
        else:
            revenue = float(rate_val)

    fuel_saved_vs_empty = pure_empty_cost - with_load_empty_cost
    net_vs_empty = revenue + fuel_saved_vs_empty  # revenue plus any fuel not burned empty
    # More intuitive: net benefit = revenue - extra empty to shipper fuel
    extra_empty_fuel = empty_to_pu * fuel_cost_per_mile
    net_benefit = revenue - extra_empty_fuel

    return {
        "empty_home_mi": round(empty_home, 0),
        "empty_to_pickup_mi": round(empty_to_pu, 0),
        "loaded_return_mi": round(loaded_mi, 0),
        "est_revenue": round(revenue, 0),
        "extra_empty_fuel": round(extra_empty_fuel, 0),
        "net_benefit_vs_empty": round(net_benefit, 0),
        "fuel_cost_per_mile": fuel_cost_per_mile,
        "weight_tons": weight_tons,
        "blurb": (
            f"Est. +${net_benefit:,.0f} vs pure empty home "
            f"(~${revenue:,.0f} revenue − ~${extra_empty_fuel:,.0f} fuel to shipper)"
            if revenue > 0
            else f"Score-only · fill rate for $ estimate · empty home ~{empty_home:.0f} mi"
        ),
    }
