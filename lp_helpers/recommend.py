"""AI Copilot: contextual, actionable recommendations for L & P Freight.

Derives suggestions from live data (no black-box ML):
- lane rate benchmark vs the primary Spruce Pine -> GA lane
- backhaul matches to kill deadhead (Lawson's core mission)
- next-best lead to call
"""

from __future__ import annotations

from typing import Any

from lp_helpers.database import PRIMARY_LANE, get_conn


def lane_benchmark_rate(weight_tons: float, loaded_miles: float, commodity: str = "") -> dict[str, float]:
    """Rule-based benchmark rate + revenue for a lane (mirrors database.calculate_rate)."""
    from lp_helpers.database import calculate_rate

    rate, revenue = calculate_rate(weight_tons, loaded_miles, loaded_miles, commodity)
    return {"rate_per_ton": rate, "revenue": revenue}


def get_recommendations(conn=None) -> list[dict[str, Any]]:
    """Return a prioritized list of suggestions for the dashboard / copilot."""
    own = conn is None
    if own:
        conn = get_conn()
    out: list[dict[str, Any]] = []
    try:
        # Backhaul opportunities: active loads with high deadhead share
        for r in conn.execute(
            "SELECT id, bol_number, deadhead_miles, loaded_miles, destination FROM loads "
            "WHERE status IN ('Accepted','In Transit','Delivered')"
        ).fetchall():
            dead = float(r["deadhead_miles"] or 0)
            loaded = float(r["loaded_miles"] or 0)
            total = dead + loaded
            if total > 0 and dead / total >= 0.35:
                pct = int(round(dead / total * 100))
                out.append({
                    "id": f"backhaul:{r['id']}",
                    "severity": "high",
                    "title": f"Backhaul from {r['destination']}",
                    "detail": f"{r['bol_number']} ran {pct}% empty. Find a return load to cut wasted miles.",
                    "screen": "Maps",
                    "cta": "View lane",
                })

        # Rate guidance for the most recent logged load
        recent = conn.execute(
            "SELECT id, bol_number, weight_tons, loaded_miles, commodity, rate_per_ton, total_revenue "
            "FROM loads WHERE status = 'Logged' ORDER BY pickup_date DESC LIMIT 1"
        ).fetchone()
        if recent:
            bench = lane_benchmark_rate(
                float(recent["weight_tons"] or 0),
                float(recent["loaded_miles"] or 0),
                recent["commodity"] or "",
            )
            actual_rate = float(recent["rate_per_ton"] or 0)
            if actual_rate and bench["rate_per_ton"]:
                gap = bench["rate_per_ton"] - actual_rate
                if gap >= 2:
                    out.append({
                        "id": f"rate:{recent['id']}",
                        "severity": "medium",
                        "title": f"Rate below benchmark on {recent['bol_number']}",
                        "detail": f"Quoted ${actual_rate:.0f}/ton vs ${bench['rate_per_ton']:.0f}/ton benchmark "
                                  f"(+${gap:.0f}/ton ≈ +${gap * float(recent['weight_tons'] or 0):,.0f}).",
                        "screen": "Rate Calculator",
                        "cta": "Re-quote",
                    })

        # Next best lead: a hot/active lead not contacted recently
        lead = conn.execute(
            "SELECT id, company, status, priority, last_contact FROM leads "
            "WHERE status IN ('Hot','Active') ORDER BY priority DESC, last_contact ASC LIMIT 1"
        ).fetchone()
        if lead:
            out.append({
                "id": f"lead:{lead['id']}",
                "severity": "medium" if lead["priority"] in ("High", "Critical") else "low",
                "title": f"Call {lead['company']}",
                "detail": f"Priority {lead['status']} lead — book the next load.",
                "screen": "Leads",
                "cta": "Open leads",
            })

        # Margin nudge when a load looks thin
        thin = conn.execute(
            "SELECT id, bol_number, total_revenue, deadhead_miles, loaded_miles FROM loads "
            "WHERE total_revenue > 0 ORDER BY total_revenue ASC LIMIT 1"
        ).fetchone()
        if thin:
            rev = float(thin["total_revenue"] or 0)
            if rev < 2500:
                out.append({
                    "id": f"margin:{thin['id']}",
                    "severity": "low",
                    "title": f"Thin margin on {thin['bol_number']}",
                    "detail": f"Only ${rev:,.0f} revenue — confirm rate or stack a backhaul.",
                    "screen": "Billing & Pay",
                    "cta": "Review",
                })
    finally:
        if own:
            conn.close()

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    out.sort(key=lambda x: order.get(x["severity"], 4))
    return out
