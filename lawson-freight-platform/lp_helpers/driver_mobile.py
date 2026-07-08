"""Mobile driver cabin UI — touch-friendly, DB-backed, Traccar GPS for Phillip / Lawson."""

from __future__ import annotations

from contextlib import closing
from datetime import date
from typing import Any, Callable

import pandas as pd
import streamlit as st

CABIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
:root {
    --cabin-bg: #0b0f14; --cabin-card: #141a22; --cabin-text: #e2e8f0;
    --cabin-muted: #94a3b8; --cabin-border: #2a3545; --cabin-orange: #f97316;
}
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, sans-serif !important;
    background: var(--cabin-bg) !important; color: var(--cabin-text) !important;
}
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { padding: 0.75rem 1rem 5rem !important; max-width: 480px !important; }
.stButton > button {
    min-height: 52px !important; font-weight: 700 !important;
    border-radius: 14px !important; background: var(--cabin-orange) !important; color: #fff !important;
}
.cabin-card {
    background: var(--cabin-card); border: 1px solid var(--cabin-border);
    border-radius: 16px; padding: 1rem; margin-bottom: 0.75rem;
}
.pill { display:inline-block; padding:0.35rem 0.75rem; border-radius:999px;
    font-size:0.8rem; font-weight:700; }
.pill-blue { background:rgba(59,130,246,0.2); color:#60a5fa; }
.pill-green { background:rgba(34,197,94,0.2); color:#4ade80; }
</style>
"""


def _default_load() -> dict[str, Any]:
    return {
        "bol_number": "—",
        "shipper": "No active load",
        "commodity": "—",
        "weight_tons": 0.0,
        "origin": "Spruce Pine, NC",
        "destination": "Central Georgia (Kohler area)",
        "status": "Available",
        "rate_per_ton": 0.0,
        "total_revenue": 0.0,
        "loaded_miles": 285,
        "deadhead_miles": 285,
        "pickup_date": str(date.today()),
    }


def fetch_active_load(get_connection: Callable[[], Any]) -> dict[str, Any]:
    try:
        with closing(get_connection()) as conn:
            row = conn.execute(
                """
                SELECT * FROM loads
                WHERE status IN ('Dispatched', 'In Transit', 'Booked')
                ORDER BY pickup_date DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return _default_load()
        return dict(row)
    except Exception:
        return _default_load()


def render_driver_app(
    *,
    get_connection: Callable[[], Any],
    get_active_owner: Callable[[], str],
    truck_label: str,
    get_traccar_fix: Callable[[], dict[str, Any] | None],
    format_sms: Callable[[str, dict[str, Any]], str],
    log_sms_event: Callable[..., None],
    on_exit: Callable[[], None] | None = None,
) -> None:
    st.markdown(CABIN_CSS, unsafe_allow_html=True)
    owner = get_active_owner()
    load = fetch_active_load(get_connection)

    top1, top2 = st.columns([3, 1])
    with top1:
        st.markdown(f"## 🚛 L & P Driver")
        st.caption(f"{owner} · {truck_label}")
    with top2:
        if st.button("Exit", use_container_width=True):
            if on_exit:
                on_exit()
            st.rerun()

    st.markdown('<div class="cabin-card">', unsafe_allow_html=True)
    st.markdown(f"**{load.get('bol_number', '—')}**")
    st.caption(
        f"{load.get('shipper', '—')} · {load.get('commodity', '—')} · "
        f"{load.get('weight_tons', 0)}t"
    )
    st.caption(f"{load.get('origin', '—')} → {load.get('destination', '—')}")
    status = str(load.get("status", "Available"))
    pill = "pill-blue" if status in ("In Transit", "Dispatched") else "pill-green"
    st.markdown(f"<span class='pill {pill}'>{status}</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Revenue", f"${float(load.get('total_revenue', 0)):,.0f}")
    c2.metric("Rate", f"${float(load.get('rate_per_ton', 0)):.2f}/t")
    c3.metric("Miles", f"{float(load.get('loaded_miles', 285)):.0f} ld")

    fix = get_traccar_fix()
    st.markdown("#### 📍 GPS")
    if fix:
        g1, g2, g3 = st.columns(3)
        g1.metric("Lat", f"{fix['latitude']:.4f}")
        g2.metric("Lon", f"{fix['longitude']:.4f}")
        g3.metric("Speed", f"{fix['speed_mph']:.0f} mph")
        st.caption(f"Live Traccar — {fix.get('device_name', 'device')}")
    else:
        st.info("Traccar offline — using Spruce Pine yard coordinates.")
        st.metric("Lat", "35.9120")
        st.metric("Lon", "-82.0640")

    tab_home, tab_update, tab_alert = st.tabs(["Home", "Update", "Alert"])

    with tab_home:
        if st.button("ACK BOL / On Site", type="primary", use_container_width=True):
            st.success(f"BOL acknowledged — {owner} on site.")

    with tab_update:
        with st.form("driver_status"):
            new_status = st.selectbox(
                "Status",
                ["Booked", "Dispatched", "In Transit", "Delivered"],
                index=["Booked", "Dispatched", "In Transit", "Delivered"].index(status)
                if status in ("Booked", "Dispatched", "In Transit", "Delivered")
                else 2,
            )
            notes = st.text_area("Driver notes", placeholder="Scale ticket, gate time, delay…")
            if st.form_submit_button("Save Status", use_container_width=True):
                load_id = load.get("id")
                if load_id:
                    try:
                        with closing(get_connection()) as conn:
                            extra = f"\n[{date.today()} {owner}] {notes}".strip() if notes else ""
                            conn.execute(
                                """
                                UPDATE loads SET status = ?,
                                    notes = COALESCE(notes, '') || ?
                                WHERE id = ?
                                """,
                                (new_status, extra, load_id),
                            )
                            conn.commit()
                        st.success(f"Status → {new_status}")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                else:
                    st.warning("Log a load in dispatch app first.")

    with tab_alert:
        arrival_msg = format_sms(
            "arrival",
            {
                "company": load.get("shipper", "Dispatch"),
                "location": load.get("destination", "Site"),
                "driver": owner,
            },
        )
        st.text_area("Arrival SMS", arrival_msg, height=120)
        if st.button("Log Arrival Alert", use_container_width=True):
            log_sms_event(None, "driver_arrival", arrival_msg, "driver_app")
            st.success("Arrival logged — send from dispatch Alerts tab.")