"""Quiet pipeline helpers — call-today queue for the existing Dashboard block.

Ports the idea of main's lp_helpers/crm.py lead_needs_call_today onto this
tree's columns (next_followup_date, last_contact) and status vocab.
Local-first: these only read/write SQLite. Nothing is texted or emailed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from lp_helpers.database import get_conn

# main crm.py ACTIVE_PIPELINE — Quoted → master's "Quote Sent"
ACTIVE_PIPELINE_STATUSES: frozenset[str] = frozenset(
    {"Hot", "Active", "New", "Contacted", "Quote Sent", "Negotiating"}
)
# Never queue these, even if a follow-up date is due. On Hold is paused, not a call.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"booked", "closed", "not interested", "on hold"}
)
STALE_CONTACT_DAYS = 3

# Back-compat alias used by tests / older call sites
OPEN_PIPELINE_STATUSES = ACTIVE_PIPELINE_STATUSES


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_date_text(value: date | datetime | str | None) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def _is_terminal_status(status: str) -> bool:
    return str(status or "").strip().lower() in TERMINAL_STATUSES


def lead_needs_call_today(
    lead: dict[str, Any],
    *,
    today: date | None = None,
    stale_days: int = STALE_CONTACT_DAYS,
) -> bool:
    """True if the lead belongs on the Dashboard follow-up queue.

    Terminal statuses (Booked / Closed / Not Interested / On Hold) are never
    included.

    Rules (OR) for everyone else — same idea as main's crm.lead_needs_call_today:
      1. next_followup_date <= today
      2. status in Hot/Active/New/Contacted/Quote Sent/Negotiating AND
         last_contact older than stale_days (or null)
      3. status Hot with null next_followup_date
    """
    today = today or date.today()
    status = str(lead.get("status") or "").strip()
    if _is_terminal_status(status):
        return False

    next_fu = _parse_date(lead.get("next_followup_date") or lead.get("next_followup_at"))
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


def _queue_label(lead: dict[str, Any], today: date) -> tuple[int | None, str]:
    next_fu = _parse_date(lead.get("next_followup_date") or lead.get("next_followup_at"))
    last = _parse_date(lead.get("last_contact"))
    if next_fu is not None and next_fu <= today:
        days = (today - next_fu).days
        if days <= 0:
            return 0, "due today"
        if days == 1:
            return 1, "1 day overdue"
        return days, f"{days} days overdue"
    if str(lead.get("status") or "") == "Hot" and next_fu is None:
        return None, "hot — no follow-up set"
    if last is None:
        return None, "no last contact"
    stale = (today - last).days
    return None, f"stale contact ({stale}d)"


def fetch_due_followups(conn=None, as_of: date | None = None) -> list[dict[str, Any]]:
    """Leads that lead_needs_call_today — dated due, stale contact, or Hot unset."""
    own = conn is None
    if own:
        conn = get_conn()
    day = as_of or date.today()
    try:
        rows = conn.execute(
            """
            SELECT id, company, contact_name, phone, status, priority,
                   last_contact, next_followup_date, followup_type, notes,
                   commodity_focus
            FROM leads
            ORDER BY priority ASC, company
            """
        ).fetchall()
    finally:
        if own:
            conn.close()

    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if not lead_needs_call_today(item, today=day):
            continue
        days, label = _queue_label(item, day)
        item["days_overdue"] = days
        item["due_label"] = label
        out.append(item)

    def _sort_key(r: dict[str, Any]) -> tuple:
        hot = 0 if str(r.get("status") or "") == "Hot" else 1
        fu = _parse_date(r.get("next_followup_date"))
        fu_ord = fu.toordinal() if fu else 10**9
        return (hot, fu_ord, str(r.get("company") or ""))

    out.sort(key=_sort_key)
    return out


def log_lead_followup(
    lead_id: int,
    *,
    next_followup_date: date | datetime | str | None,
    followup_type: str = "Phone Call",
    note: str = "",
    outcome: str = "Followed up",
    status: str | None = None,
    message: str | None = None,
    channel: str | None = None,
    conn=None,
) -> dict[str, Any]:
    """Record a follow-up: last_contact, next date, call_logs, optional sms_log.

    Does not send SMS or email. ``message`` is stored locally as clipboard-only.
    """
    own = conn is None
    if own:
        conn = get_conn()
    try:
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if lead is None:
            raise ValueError(f"Lead {lead_id} not found")

        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M")
        next_s = _as_date_text(next_followup_date)
        prior_notes = lead["notes"] if "notes" in lead.keys() and lead["notes"] else ""
        combined = f"[{ts}] {note}\n{prior_notes}" if note else prior_notes

        fields = [
            "last_contact = ?",
            "next_followup_date = ?",
            "followup_type = ?",
            "notes = ?",
        ]
        values: list[Any] = [ts, next_s, followup_type, combined]
        if status:
            fields.append("status = ?")
            values.append(status)
        values.append(lead_id)
        conn.execute(
            f"UPDATE leads SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.execute(
            """
            INSERT INTO call_logs (lead_id, call_type, notes, outcome)
            VALUES (?,?,?,?)
            """,
            (lead_id, followup_type, note or f"Follow-up logged ({followup_type})", outcome),
        )

        sms_id = None
        if message:
            cur = conn.execute(
                """
                INSERT INTO sms_log (lead_id, alert_type, message, sent_via)
                VALUES (?,?,?,?)
                """,
                (lead_id, channel or followup_type, message, "clipboard"),
            )
            sms_id = cur.lastrowid

        if own:
            conn.commit()
        return {
            "lead_id": lead_id,
            "last_contact": ts,
            "next_followup_date": next_s,
            "followup_type": followup_type,
            "sms_log_id": sms_id,
        }
    finally:
        if own:
            conn.close()
