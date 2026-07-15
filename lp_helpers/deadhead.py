"""Deadhead minimization — simple return-load scoring for bulk lanes.

Designed for 1-5 truck SE bulk haulers (e.g. GA delivery → back toward W NC).
Scoring is transparent rules — not ML. Fast to ship, easy to explain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Default home base (western NC / Spruce Pine corridor)
DEFAULT_HOME = "Spruce Pine, NC"
DEFAULT_DELIVERY_ZONE = "Central Georgia"

# Rough highway corridor keywords that reduce empty miles toward home
HOMEBOUND_KEYWORDS: tuple[str, ...] = (
    "nc",
    "north carolina",
    "spruce pine",
    "asheville",
    "marion",
    "hickory",
    "charlotte",
    "boone",
    "burnsville",
    "mitchell",
    "avery",
    "19e",
    "hwy 226",
    "i-26",
    "i-40",
    "tennessee",
    "tn",
    "virginia",
    "va",
)

# Bulk / end-dump friendly commodities
BULK_KEYWORDS: tuple[str, ...] = (
    "feldspar",
    "mica",
    "quartz",
    "clay",
    "sand",
    "gravel",
    "aggregate",
    "lime",
    "rock",
    "dirt",
    "mulch",
    "fertilizer",
    "bulk",
    "stone",
    "ash",
)


@dataclass
class DeadheadScore:
    """Transparent score for a return-load candidate."""

    score: int  # 0-100
    grade: str  # A/B/C/D
    label: str
    reasons: list[str]
    empty_miles_estimate: float | None = None
    source: str = "rules"


def _text_blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def grade_from_score(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 45:
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
) -> DeadheadScore:
    """Score how well a candidate reduces empty miles toward home.

    Transparent points (max ~100):
      +40  destination pulls toward home corridor
      +20  origin is near current delivery zone (can book soon)
      +20  bulk / end-dump friendly commodity
      +10  rate looks decent (if provided)
      +10  notes mention backhaul / return / northbound
      -15  destination is deeper south / away from home
    """
    score = 30  # baseline: any paying load beats pure empty
    reasons: list[str] = []
    blob_dest = _text_blob(destination, notes)
    blob_origin = _text_blob(origin, notes)
    blob_all = _text_blob(origin, destination, commodity, notes, rate_hint)
    home_l = home.lower()
    cur_l = current_location.lower()

    # Destination toward home
    home_hits = sum(1 for k in HOMEBOUND_KEYWORDS if k in blob_dest)
    if home_l.split(",")[0] in blob_dest or "spruce pine" in blob_dest:
        score += 40
        reasons.append("Destination points home / W NC")
    elif home_hits >= 2:
        score += 35
        reasons.append("Destination on homebound corridor")
    elif home_hits == 1:
        score += 20
        reasons.append("Partial homebound signal")
    else:
        score -= 5
        reasons.append("Destination not clearly homebound")

    # Can pick up near where we are (GA delivery zone)
    ga_tokens = ("ga", "georgia", "kohler", "atlanta", "macon", "augusta", "savannah")
    if any(t in blob_origin for t in ga_tokens) or any(t in cur_l for t in ga_tokens if t in blob_origin):
        score += 20
        reasons.append("Pickup near current GA area")
    elif "sc" in blob_origin or "south carolina" in blob_origin:
        score += 10
        reasons.append("Pickup nearby SE (SC)")

    # Trailer fit
    if any(k in _text_blob(commodity) for k in BULK_KEYWORDS):
        score += 20
        reasons.append("Bulk / end-dump friendly commodity")
    elif commodity:
        score += 5
        reasons.append("Commodity present — verify trailer fit")

    # Rate hint (very light)
    rate_val = None
    if isinstance(rate_hint, (int, float)):
        rate_val = float(rate_hint)
    elif rate_hint:
        digits = "".join(c if c.isdigit() or c == "." else " " for c in str(rate_hint))
        parts = [p for p in digits.split() if p]
        if parts:
            try:
                rate_val = float(parts[0])
            except ValueError:
                rate_val = None
    if rate_val is not None:
        if rate_val >= 45:
            score += 10
            reasons.append(f"Rate looks solid ({rate_val:g})")
        elif rate_val >= 35:
            score += 5
            reasons.append(f"Rate acceptable ({rate_val:g})")
        else:
            reasons.append(f"Rate low ({rate_val:g}) — only if empty otherwise")

    if any(w in blob_all for w in ("backhaul", "return", "northbound", "head home", "deadhead")):
        score += 10
        reasons.append("Marked as backhaul / return intent")

    # Deeper south penalty
    if any(w in blob_dest for w in ("florida", "fl ", "miami", "tampa", "orlando")):
        score -= 15
        reasons.append("Further south increases empty risk later")

    score = max(0, min(100, score))
    grade = grade_from_score(score)
    if grade == "A":
        label = "Strong homebound backhaul"
    elif grade == "B":
        label = "Good deadhead reducer"
    elif grade == "C":
        label = "Maybe — check miles & rate"
    else:
        label = "Weak — empty may be better"

    return DeadheadScore(
        score=score,
        grade=grade,
        label=label,
        reasons=reasons,
        empty_miles_estimate=empty_miles_estimate,
        source="rules",
    )


def rank_return_candidates(
    candidates: list[dict[str, Any]],
    *,
    home: str = DEFAULT_HOME,
    current_location: str = DEFAULT_DELIVERY_ZONE,
) -> list[tuple[dict[str, Any], DeadheadScore]]:
    """Score and sort candidates best-first."""
    ranked: list[tuple[dict[str, Any], DeadheadScore]] = []
    for c in candidates:
        sc = score_return_load(
            origin=str(c.get("origin") or c.get("lane") or ""),
            destination=str(c.get("destination") or c.get("lane") or ""),
            commodity=str(c.get("commodity") or ""),
            rate_hint=c.get("rate") or c.get("rate_per_ton"),
            notes=str(c.get("notes") or c.get("contact") or ""),
            home=home,
            current_location=current_location,
        )
        ranked.append((c, sc))
    ranked.sort(key=lambda x: x[1].score, reverse=True)
    return ranked


def opportunities_as_candidates(opportunities_df: Any) -> list[dict[str, Any]]:
    """Convert a DataFrame/records of board opportunities into scorer dicts."""
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
        origin, destination = lane, lane
        if "→" in lane:
            parts = [p.strip() for p in lane.split("→", 1)]
            origin, destination = parts[0], parts[1]
        elif "->" in lane:
            parts = [p.strip() for p in lane.split("->", 1)]
            origin, destination = parts[0], parts[1]
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
