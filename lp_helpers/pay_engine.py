"""Driver pay engine for L & P Freight.

Core policy (Lawson's rule):
    Drivers are ALWAYS paid for the miles they actually drove — regardless of the
    Google/planned route. If a driver runs Asheville -> Johnson City -> Nashville
    instead of I-40, or Google shorts the lane by 30 miles, the driver is still
    paid for every mile actually driven.

Google/planned mileage is REFERENCE ONLY. A large deviation is *flagged* for
dispatcher review (possible inefficiency or fraud) but never silently reduces
driver pay.

This module is intentionally pure (no Streamlit, no SQLite) so it can be unit
tested and reused by the UI, the settlement flow, and the ELD ingest pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class PayResult:
    pay_loaded_miles: float
    pay_empty_miles: float
    loaded_rate: float
    empty_rate: float
    loaded_pay: float
    empty_pay: float
    base_pay: float
    bonuses: float
    accessorials: float
    deductions: float
    total_pay: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def driver_pay(
    actual_loaded_miles: float,
    actual_empty_miles: float,
    loaded_rate: float,
    empty_rate: float,
    bonuses: float = 0.0,
    accessorials: float = 0.0,
    deductions: float = 0.0,
) -> PayResult:
    """Compute driver pay on ACTUAL miles driven (Lawson's rule).

    Negative mileage inputs are clamped to zero. Pay always reflects the miles
    the driver actually ran, never the planned/Google estimate.
    """
    al = max(0.0, float(actual_loaded_miles or 0.0))
    ae = max(0.0, float(actual_empty_miles or 0.0))
    lr = float(loaded_rate or 0.0)
    er = float(empty_rate or 0.0)

    loaded_pay = round(al * lr, 2)
    empty_pay = round(ae * er, 2)
    base_pay = round(loaded_pay + empty_pay, 2)
    total_pay = round(base_pay + float(bonuses) + float(accessorials) - float(deductions), 2)

    return PayResult(
        pay_loaded_miles=round(al, 1),
        pay_empty_miles=round(ae, 1),
        loaded_rate=lr,
        empty_rate=er,
        loaded_pay=loaded_pay,
        empty_pay=empty_pay,
        base_pay=base_pay,
        bonuses=round(float(bonuses), 2),
        accessorials=round(float(accessorials), 2),
        deductions=round(float(deductions), 2),
        total_pay=total_pay,
    )


def mileage_reconciliation(
    actual_loaded_miles: float,
    actual_empty_miles: float,
    google_miles: float | None = None,
    planned_loaded_miles: float = 0.0,
    planned_empty_miles: float = 0.0,
    tolerance_pct: float = 10.0,
) -> dict[str, Any]:
    """Reconcile actual miles against the Google/planned basis.

    `pay_miles` is ALWAYS the actual total — this function never changes pay, it
    only reports how far actual deviated from the reference basis and whether that
    deviation should be flagged for a human to review.
    """
    actual_total = round(max(0.0, actual_loaded_miles or 0.0) + max(0.0, actual_empty_miles or 0.0), 1)
    planned_total = round((planned_loaded_miles or 0.0) + (planned_empty_miles or 0.0), 1)

    if google_miles and google_miles > 0:
        basis = round(float(google_miles), 1)
        basis_source = "google"
    elif planned_total > 0:
        basis = planned_total
        basis_source = "planned"
    else:
        basis = 0.0
        basis_source = "none"

    if basis > 0:
        variance_pct = round((actual_total - basis) / basis * 100.0, 1)
        extra_miles = round(actual_total - basis, 1)
    else:
        variance_pct = 0.0
        extra_miles = 0.0

    flagged = basis > 0 and abs(variance_pct) > tolerance_pct

    return {
        "pay_miles": actual_total,          # always actual — the miles they drove
        "basis_miles": basis,
        "basis_source": basis_source,
        "extra_miles": extra_miles,          # + = drove more than basis (e.g. Google short)
        "variance_pct": variance_pct,
        "flagged": flagged,
        "tolerance_pct": tolerance_pct,
    }


def pay_decision(
    actual_loaded_miles: float,
    actual_empty_miles: float,
    loaded_rate: float,
    empty_rate: float,
    google_miles: float | None = None,
    planned_loaded_miles: float = 0.0,
    planned_empty_miles: float = 0.0,
    bonuses: float = 0.0,
    accessorials: float = 0.0,
    deductions: float = 0.0,
    tolerance_pct: float = 10.0,
) -> dict[str, Any]:
    """Return an actionable pay decision (Decisions Over Data).

    Includes the total the driver is owed (on actual miles) plus the dollar
    impact versus what a Google/planned-based payout would have been, and a plain
    English recommendation for the dispatcher.
    """
    pay = driver_pay(
        actual_loaded_miles, actual_empty_miles, loaded_rate, empty_rate,
        bonuses=bonuses, accessorials=accessorials, deductions=deductions,
    )
    recon = mileage_reconciliation(
        actual_loaded_miles, actual_empty_miles, google_miles,
        planned_loaded_miles, planned_empty_miles, tolerance_pct,
    )

    actual_total = pay.pay_loaded_miles + pay.pay_empty_miles
    blended_rate = (pay.base_pay / actual_total) if actual_total > 0 else 0.0
    # What the base pay WOULD have been on the Google/planned basis:
    basis_base_pay = round(recon["basis_miles"] * blended_rate, 2) if recon["basis_miles"] > 0 else pay.base_pay
    dollar_impact = round(pay.base_pay - basis_base_pay, 2)  # + = driver earns more than basis

    if recon["basis_source"] == "none":
        message = f"Paying {actual_total:.0f} actual miles — ${pay.total_pay:,.2f}. No reference mileage on file."
    elif recon["extra_miles"] > 0:
        message = (
            f"Driver drove {recon['extra_miles']:.0f} mi MORE than {recon['basis_source']} "
            f"({recon['basis_miles']:.0f} mi). Paying actual {actual_total:.0f} mi "
            f"= +${dollar_impact:,.2f} to the driver. Per L&P policy, they are paid for miles driven."
        )
    elif recon["extra_miles"] < 0:
        message = (
            f"Driver drove {abs(recon['extra_miles']):.0f} mi LESS than {recon['basis_source']} "
            f"({recon['basis_miles']:.0f} mi). Paying actual {actual_total:.0f} mi "
            f"= ${dollar_impact:,.2f} vs basis."
        )
    else:
        message = f"Actual matches {recon['basis_source']} basis. Paying {actual_total:.0f} mi — ${pay.total_pay:,.2f}."

    if recon["flagged"]:
        message += f" ⚠️ Variance {recon['variance_pct']:+.1f}% exceeds ±{tolerance_pct:.0f}% — review route."

    return {
        "pay": pay.to_dict(),
        "total_pay": pay.total_pay,
        "pay_miles": recon["pay_miles"],
        "basis_miles": recon["basis_miles"],
        "basis_source": recon["basis_source"],
        "extra_miles": recon["extra_miles"],
        "variance_pct": recon["variance_pct"],
        "flagged": recon["flagged"],
        "dollar_impact_vs_basis": dollar_impact,
        "message": message,
    }
