"""AI capability ports — human confirms all suggestions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RateSuggestion:
    rate_per_ton: float
    total_revenue: float
    rationale: str
    confidence: float = 0.5
    source: str = "rules"


@dataclass
class LoadMatch:
    opportunity_id: Any
    score: float
    rationale: str
    source: str = "rules"


class RateOptimizer(Protocol):
    def suggest(
        self,
        *,
        commodity: str,
        weight_tons: float,
        loaded_miles: float,
        deadhead_miles: float,
        context: dict[str, Any] | None = None,
    ) -> RateSuggestion: ...


class LoadMatcher(Protocol):
    def rank(
        self,
        opportunities: list[dict[str, Any]],
        *,
        trailer_type: str = "end_dump",
        home_origin: str = "",
        context: dict[str, Any] | None = None,
    ) -> list[LoadMatch]: ...


@dataclass
class RulesRateOptimizer:
    """v1: deterministic quote assist from baseline lane economics."""

    baseline_per_ton: float = 48.0

    def suggest(
        self,
        *,
        commodity: str,
        weight_tons: float,
        loaded_miles: float,
        deadhead_miles: float,
        context: dict[str, Any] | None = None,
    ) -> RateSuggestion:
        context = context or {}
        mult = 1.0
        c = commodity.lower()
        if any(x in c for x in ("feldspar", "mica", "quartz")):
            mult = 1.02
        elif "fertilizer" in c:
            mult = 1.03
        rate = round(self.baseline_per_ton * mult, 2)
        # Penalize high deadhead share lightly in suggested floor
        total_miles = max(loaded_miles + deadhead_miles, 1.0)
        deadhead_share = deadhead_miles / total_miles
        if deadhead_share > 0.35:
            rate = round(rate * 1.05, 2)
        total = round(rate * max(weight_tons, 0), 2)
        rationale = (
            f"Baseline ${self.baseline_per_ton:.2f}/t × commodity factor {mult:.2f}; "
            f"deadhead share {deadhead_share:.0%}."
        )
        return RateSuggestion(
            rate_per_ton=rate,
            total_revenue=total,
            rationale=rationale,
            confidence=0.55,
            source="rules",
        )


@dataclass
class RulesLoadMatcher:
    """v1: rank board rows by simple keyword / lane affinity."""

    preferred_commodities: tuple[str, ...] = field(
        default_factory=lambda: ("feldspar", "mica", "quartz", "clay", "aggregate")
    )

    def rank(
        self,
        opportunities: list[dict[str, Any]],
        *,
        trailer_type: str = "end_dump",
        home_origin: str = "",
        context: dict[str, Any] | None = None,
    ) -> list[LoadMatch]:
        _ = trailer_type, context
        matches: list[LoadMatch] = []
        home = home_origin.lower()
        for opp in opportunities:
            score = 0.3
            reasons: list[str] = []
            commodity = str(opp.get("commodity") or "").lower()
            lane = str(opp.get("lane") or "").lower()
            if any(p in commodity for p in self.preferred_commodities):
                score += 0.4
                reasons.append("commodity fit")
            if home and home.split(",")[0] in lane:
                score += 0.25
                reasons.append("near home lane")
            matches.append(
                LoadMatch(
                    opportunity_id=opp.get("id"),
                    score=min(score, 1.0),
                    rationale=", ".join(reasons) or "general board option",
                    source="rules",
                )
            )
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches
