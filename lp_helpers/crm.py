"""CRM call-today queue helpers — follow-up dates and hot-lead nudges."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

# Statuses that deserve a call if contact is stale
ACTIVE_PIPELINE_STATUSES = frozenset(
    {"Hot", "New", "Contacted", "Negotiating", "Quoted", "Active"}
)
# Never put these on the call-today queue (even if follow-up date is due)
TERMINAL_STATUSES = frozenset(
    {
        "closed",
        "lost",
        "inactive",
        "do not call",
        "do_not_call",
        "dnc",
        "won",
        "dead",
    }
)
STALE_CONTACT_DAYS = 3


def _parse_date(val: Any) -> date | None:
    if val is None or val == "":
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None


def _is_terminal_status(status: str) -> bool:
    return str(status or "").strip().lower() in TERMINAL_STATUSES


def lead_needs_call_today(
    lead: dict[str, Any],
    *,
    today: date | None = None,
    stale_days: int = STALE_CONTACT_DAYS,
) -> bool:
    """True if lead belongs on the Call-today queue.

    Terminal statuses (Closed/Lost/Inactive/DNC) are never included.

    Rules (OR) for non-terminal leads:
      1. next_followup_at <= today
      2. status in Hot/New/Contacted/Negotiating (+ Quoted/Active) AND
         last_contact older than stale_days (or null)
      3. status Hot with null next_followup_at
    """
    today = today or date.today()
    status = str(lead.get("status") or "").strip()
    if _is_terminal_status(status):
        return False

    next_fu = _parse_date(lead.get("next_followup_at"))
    last = _parse_date(lead.get("last_contact"))

    if next_fu is not None and next_fu <= today:
        return True
    if status == "Hot" and next_fu is None:
        return True
    if status in ACTIVE_PIPELINE_STATUSES:
        if last is None:
            return True
        if last <= today - timedelta(days=stale_days):
            return True
    return False


def filter_call_today_leads(
    leads: list[dict[str, Any]] | Any,
    *,
    today: date | None = None,
    stale_days: int = STALE_CONTACT_DAYS,
) -> list[dict[str, Any]]:
    """Filter leads (list of dicts or DataFrame) to call-today set."""
    today = today or date.today()
    records: list[dict[str, Any]]
    if leads is None:
        return []
    if hasattr(leads, "to_dict"):
        try:
            if getattr(leads, "empty", False):
                return []
            records = leads.to_dict("records")
        except Exception:
            return []
    else:
        records = list(leads)

    out = [r for r in records if lead_needs_call_today(r, today=today, stale_days=stale_days)]

    def _sort_key(r: dict[str, Any]) -> tuple:
        st = str(r.get("status") or "")
        hot = 0 if st == "Hot" else 1
        fu = _parse_date(r.get("next_followup_at"))
        fu_ord = fu.toordinal() if fu else 10**9
        return (hot, fu_ord, str(r.get("company") or ""))

    out.sort(key=_sort_key)
    return out


def next_followup_iso(*, days: int = 3, today: date | None = None) -> str:
    """Local-date ISO string for next follow-up (avoids SQLite UTC date('now'))."""
    base = today or date.today()
    return (base + timedelta(days=days)).isoformat()
