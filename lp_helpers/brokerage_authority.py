"""
Brokerage Authority Widget — in-app status of MC/DOT/EIN/insurance/BMC-84
with due-date reminders. Reads from the compliance table and adds brokerage-specific items.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from lp_helpers.database import get_conn, get_setting, set_setting


# ===========================================================================
# Brokerage authority items
# ===========================================================================

BROKERAGE_AUTHORITY_ITEMS: list[dict[str, Any]] = [
    {
        "item": "LLC Formation (NC Secretary of State)",
        "category": "Legal Entity",
        "status": "Not Started",
        "due_date": None,
        "notes": "File with NC Secretary of State — required before EIN",
        "priority": 1,
    },
    {
        "item": "EIN (Employer ID Number)",
        "category": "Tax ID",
        "status": "Not Started",
        "due_date": None,
        "notes": "Free via IRS after LLC formation",
        "priority": 2,
    },
    {
        "item": "USDOT Number",
        "category": "Authority",
        "status": "Not Started",
        "due_date": None,
        "notes": "FMCSA registration — required to operate CMVs interstate",
        "priority": 3,
    },
    {
        "item": "MC Number (Broker Authority)",
        "category": "Authority",
        "status": "Not Started",
        "due_date": None,
        "notes": "FMCSA — 'Broker of Property' authority for brokerage",
        "priority": 4,
    },
    {
        "item": "BOC-3 Filing (Process Agent)",
        "category": "Compliance",
        "status": "Not Started",
        "due_date": None,
        "notes": "Required before authority activates — file with FMCSA",
        "priority": 5,
    },
    {
        "item": "UCR Registration",
        "category": "Compliance",
        "status": "Not Started",
        "due_date": "2026-12-31",
        "notes": "Annual interstate registration — renews yearly",
        "priority": 6,
    },
    {
        "item": "Liability Insurance ($750k-$1M)",
        "category": "Insurance",
        "status": "Not Started",
        "due_date": None,
        "notes": "FMCSA minimum auto liability — confirm bulk/mineral coverage",
        "priority": 7,
    },
    {
        "item": "Cargo Insurance",
        "category": "Insurance",
        "status": "Not Started",
        "due_date": None,
        "notes": "Covers freight (feldspar/mica/aggregate) — confirm bulk exclusions",
        "priority": 8,
    },
    {
        "item": "BMC-84 Broker Surety Bond ($75k)",
        "category": "Bond",
        "status": "Not Started",
        "due_date": None,
        "notes": "Required for brokerage authority — or BMC-85 trust alternative",
        "priority": 9,
    },
    {
        "item": "Contingent Cargo / Broker Liability",
        "category": "Insurance",
        "status": "Not Started",
        "due_date": None,
        "notes": "Protects brokerage vs carrier failures — recommended",
        "priority": 10,
    },
    {
        "item": "IFTA Fuel Tax Reporting",
        "category": "Tax",
        "status": "Active",
        "due_date": "2026-07-31",
        "notes": "Quarterly IFTA — import fuel CSV here",
        "priority": 11,
    },
    {
        "item": "Drug & Alcohol Consortium",
        "category": "Compliance",
        "status": "Required",
        "due_date": "2026-09-01",
        "notes": "CDL interstate requirement",
        "priority": 12,
    },
    {
        "item": "Driver Qualification File",
        "category": "Compliance",
        "status": "In Progress",
        "due_date": None,
        "notes": "CDL, med card, MVR, road test",
        "priority": 13,
    },
]


def seed_brokerage_authority_items() -> None:
    """Seed brokerage authority items into compliance table if not present."""
    conn = get_conn()
    existing = {row["item"] for row in conn.execute("SELECT item FROM compliance").fetchall()}
    for item in BROKERAGE_AUTHORITY_ITEMS:
        if item["item"] not in existing:
            conn.execute(
                "INSERT INTO compliance (item, status, due_date, notes) VALUES (?,?,?,?)",
                (item["item"], item["status"], item["due_date"], item["notes"]),
            )
    conn.commit()
    conn.close()


def fetch_brokerage_status() -> pd.DataFrame:
    """Fetch all compliance items, including brokerage-specific ones."""
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM compliance ORDER BY due_date", conn)
    conn.close()
    return df


def update_brokerage_item(item_id: int, status: str, notes: str | None = None) -> None:
    """Update a brokerage authority item's status and notes."""
    conn = get_conn()
    if notes is not None:
        conn.execute(
            "UPDATE compliance SET status = ?, notes = ?, updated_at = datetime('now') WHERE id = ?",
            (status, notes, item_id),
        )
    else:
        conn.execute(
            "UPDATE compliance SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, item_id),
        )
    conn.commit()
    conn.close()


def get_brokerage_progress() -> dict[str, Any]:
    """Compute overall brokerage authority progress."""
    df = fetch_brokerage_status()
    if df.empty:
        return {"total": 0, "completed": 0, "in_progress": 0, "not_started": 0, "pct": 0}

    total = len(df)
    completed = int((df["status"].str.lower().isin(["completed", "active", "verified"])).sum())
    in_progress = int((df["status"].str.lower().isin(["in progress", "due soon", "required"])).sum())
    not_started = int((df["status"].str.lower() == "not started").sum())
    pct = round((completed / total * 100), 1) if total > 0 else 0

    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
        "pct": pct,
    }


def get_due_soon_items(days_ahead: int = 30) -> list[dict[str, Any]]:
    """Get items due within the next N days."""
    df = fetch_brokerage_status()
    if df.empty:
        return []

    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    due_soon = []

    for _, row in df.iterrows():
        due = row.get("due_date")
        if due and str(due).strip():
            try:
                due_dt = datetime.strptime(str(due)[:10], "%Y-%m-%d").date()
                if today <= due_dt <= cutoff:
                    days_remaining = (due_dt - today).days
                    due_soon.append({
                        "id": int(row["id"]),
                        "item": str(row["item"]),
                        "status": str(row["status"]),
                        "due_date": str(due)[:10],
                        "days_remaining": days_remaining,
                        "notes": str(row.get("notes", "") or ""),
                    })
            except (ValueError, TypeError):
                pass

    return sorted(due_soon, key=lambda x: x["days_remaining"])


# ===========================================================================
# UI Render
# ===========================================================================

def render_brokerage_authority_widget() -> None:
    """Render the Brokerage Authority Widget in the app."""
    st.markdown('<div class="lf-page-title">✅ Brokerage Authority</div>', unsafe_allow_html=True)
    st.caption("MC/DOT/EIN/insurance/BMC-84 status tracker with due-date reminders")

    # Seed items if needed
    seed_brokerage_authority_items()

    # Progress overview
    progress = get_brokerage_progress()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Items", progress["total"])
    c2.metric("Completed", progress["completed"], delta=f"{progress['pct']}%")
    c3.metric("In Progress", progress["in_progress"])
    c4.metric("Not Started", progress["not_started"])

    # Progress bar
    st.progress(progress["pct"] / 100.0, text=f"Brokerage Setup: {progress['pct']}% complete")

    # Due-soon reminders
    due_soon = get_due_soon_items(days_ahead=30)
    if due_soon:
        st.warning(f"⚠️ {len(due_soon)} item(s) due within 30 days")
        for item in due_soon:
            st.markdown(
                f"<div style='padding:0.5rem;border-left:4px solid #ea580c;background:#fff7ed;"
                f"border-radius:6px;margin-bottom:0.4rem;'>"
                f"<b>{item['item']}</b> — Due {item['due_date']} "
                f"({item['days_remaining']} day{'s' if item['days_remaining'] != 1 else ''} remaining)"
                f"<br><span style='color:#64748b;font-size:0.85rem;'>{item['notes']}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # Full authority table
    df = fetch_brokerage_status()
    if df.empty:
        st.info("No compliance items configured.")
        return

    st.markdown("#### All Authority & Compliance Items")

    # Color-code status
    def status_pill(status: str) -> str:
        s = status.lower()
        if s in ("completed", "active", "verified"):
            return f'<span class="lf-pill green"><span class="lf-dot"></span>{status}</span>'
        elif s in ("in progress", "due soon", "required"):
            return f'<span class="lf-pill amber"><span class="lf-dot"></span>{status}</span>'
        elif s == "not started":
            return f'<span class="lf-pill red"><span class="lf-dot"></span>{status}</span>'
        else:
            return f'<span class="lf-pill blue"><span class="lf-dot"></span>{status}</span>'

    for _, row in df.iterrows():
        due = str(row.get("due_date", "") or "")[:10] if row.get("due_date") else "—"
        st.markdown(
            f"<div class='lf-card'>"
            f"<div class='lf-row'><b>{row['item']}</b>{status_pill(row['status'])}</div>"
            f"<div class='lf-muted'>Due: {due} · {row.get('notes', '') or '—'}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Inline update
        col1, col2 = st.columns([3, 1])
        with col1:
            new_status = st.selectbox(
                "Status",
                ["Not Started", "In Progress", "Completed", "Active", "Verified", "Required", "Pending"],
                index=["Not Started", "In Progress", "Completed", "Active", "Verified", "Required", "Pending"]
                .index(row["status"]) if row["status"] in ["Not Started", "In Progress", "Completed", "Active", "Verified", "Required", "Pending"] else 0,
                key=f"broker_status_{row['id']}",
                label_visibility="collapsed",
            )
        with col2:
            if st.button("Update", key=f"broker_upd_{row['id']}", use_container_width=True):
                update_brokerage_item(int(row["id"]), new_status)
                st.success(f"{row['item']} → {new_status}")
                st.rerun()

    # Quick stats
    st.markdown("---")
    st.markdown("#### Brokerage Readiness Checklist")
    completed_items = df[df["status"].str.lower().isin(["completed", "active", "verified"])]
    total_items = len(df)
    st.markdown(f"- **{len(completed_items)}/{total_items}** items completed")
    st.markdown(f"- **{progress['pct']}%** overall progress")

    if progress["pct"] == 100:
        st.success("🎉 All brokerage authority items complete! Ready to broker.")
    elif progress["pct"] >= 75:
        st.info("Almost there — finish the remaining items to start brokering.")
    elif progress["pct"] >= 50:
        st.warning("Halfway — prioritize insurance and bond items.")
    else:
        st.error("Brokerage setup is early stage. Start with LLC formation and EIN.")