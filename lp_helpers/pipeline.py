"""Quiet pipeline helpers — due follow-ups and opportunity status.

Local-first: these only read/write SQLite. Nothing is texted or emailed.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from lp_helpers.database import get_conn

# Closed-out leads stay off the due list even if a stale date remains.
_INACTIVE_LEAD_STATUSES = frozenset({"Closed", "Not Interested"})


def _parse_followup_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_date_text(value: date | datetime | str | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    parsed = _parse_followup_date(value)
    return parsed.isoformat() if parsed else str(value).strip()[:10] or None


def fetch_due_followups(conn=None, as_of: date | None = None) -> list[dict[str, Any]]:
    """Leads whose next_followup_date is today or in the past.

    Ignores blank dates. Does not filter by Hot/Active/New — seed data uses
    Hot while the schema default is Active, and any scheduled date should show.
    Closed / Not Interested leads are omitted so the list stays quiet.
    """
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
            WHERE next_followup_date IS NOT NULL
              AND TRIM(next_followup_date) != ''
              AND date(next_followup_date) <= date(?)
            ORDER BY date(next_followup_date) ASC, priority ASC, company
            """,
            (day.isoformat(),),
        ).fetchall()
    finally:
        if own:
            conn.close()

    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if (item.get("status") or "") in _INACTIVE_LEAD_STATUSES:
            continue
        due = _parse_followup_date(item.get("next_followup_date"))
        if due is None:
            continue
        days = (day - due).days
        item["days_overdue"] = days
        if days <= 0:
            item["due_label"] = "due today"
        elif days == 1:
            item["due_label"] = "1 day overdue"
        else:
            item["due_label"] = f"{days} days overdue"
        out.append(item)
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
