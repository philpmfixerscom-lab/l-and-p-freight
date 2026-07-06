"""
L & P Freight — Mobile Driver App (bottom-nav, large touch targets, dark cabin mode).

Run standalone:
    streamlit run mobile_app.py --server.port 8503

Or from main app via ?page=driver query param.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

try:
    from eld_integration import ELDClient, VehicleLocation, DriverHos
    from portal import fetch_customers, fetch_purchase_orders, fetch_po_loads, get_customer_po_summary
    from routing_editor import fetch_routes, route_variance_analysis
except ImportError:
    pass

ASSETS = [
    {"id": 1, "type": "Truck+Trailer", "name": "Tractor + 39ft End-Dump", "loaded": 1.75, "empty": 0.85},
    {"id": 2, "type": "Truck+Trailer", "name": "Backup Rig", "loaded": 1.65, "empty": 0.80},
    {"id": 3, "type": "Trailer", "name": "39ft End-Dump Only", "loaded": 1.50, "empty": 0.75},
]

CURRENT_LOAD = {
    "bol_number": "LP-20260706-01",
    "shipper": "Sibelco",
    "commodity": "Feldspar",
    "weight_tons": 24,
    "origin": "Spruce Pine, NC",
    "destination": "Central Georgia (Kohler)",
    "status": "In Transit",
    "rate_per_ton": 48.0,
    "total_revenue": 1152.0,
    "loaded_miles": 285,
    "empty_miles": 285,
    "pickup_date": str(date.today()),
}

st.set_page_config(
    page_title="L & P Driver",
    layout="wide",
    page_icon="🚛",
    initial_sidebar_state="collapsed",
)

CABIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

:root {
    --cabin-bg: #0b0f14;
    --cabin-card: #141a22;
    --cabin-card-2: #1c2430;
    --cabin-text: #e2e8f0;
    --cabin-muted: #94a3b8;
    --cabin-border: #2a3545;
    --cabin-green: #22c55e;
    --cabin-amber: #f59e0b;
    --cabin-red: #ef4444;
    --cabin-blue: #3b82f6;
    --cabin-orange: #f97316;
    --cabin-touch: 52px;
}

html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    background: var(--cabin-bg) !important;
    color: var(--cabin-text) !important;
}

#MainMenu, footer, header[data-testid="stHeader"] {
    visibility: hidden; height: 0;
}

.block-container {
    padding: 0.75rem 1rem 6rem !important;
    max-width: 100% !important;
}

.stTabs [data-baseweb="tab"] {
    font-size: 0.85rem !important;
    font-weight: 700 !important;
    padding: 0.6rem 0.5rem !important;
    color: var(--cabin-muted) !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: var(--cabin-orange) !important;
}

div[data-testid="stMetric"] {
    background: var(--cabin-card);
    border: 1px solid var(--cabin-border);
    border-radius: 14px;
    padding: 0.9rem;
}
div[data-testid="stMetric"] label {
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    color: var(--cabin-muted) !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-size: 1.5rem !important;
    font-weight: 800 !important;
    color: var(--cabin-text) !important;
}

.stButton > button {
    min-height: var(--cabin-touch) !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    border-radius: 14px !important;
    border: none !important;
    background: var(--cabin-orange) !important;
    color: white !important;
    padding: 0 1.25rem !important;
    box-shadow: 0 4px 0 #c2410c;
    transition: transform 0.1s, box-shadow 0.1s;
}
.stButton > button:active {
    transform: translateY(2px);
    box-shadow: 0 1px 0 #c2410c;
}
.stButton > button[kind="secondary"] {
    background: var(--cabin-card-2) !important;
    color: var(--cabin-text) !important;
    border: 1px solid var(--cabin-border) !important;
    box-shadow: none;
}

.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox > div > div {
    min-height: var(--cabin-touch) !important;
    font-size: 1rem !important;
    border-radius: 12px !important;
    border: 1px solid var(--cabin-border) !important;
    background: var(--cabin-card) !important;
    color: var(--cabin-text) !important;
}

div[data-testid="stForm"] {
    background: var(--cabin-card);
    border: 1px solid var(--cabin-border);
    border-radius: 16px;
    padding: 1rem;
}

.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
}

.cabin-card {
    background: var(--cabin-card);
    border: 1px solid var(--cabin-border);
    border-radius: 16px;
    padding: 1rem;
    margin-bottom: 0.75rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}

.cabin-card-2 {
    background: var(--cabin-card-2);
    border: 1px solid var(--cabin-border);
    border-radius: 14px;
    padding: 0.85rem;
}

.cabin-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--cabin-muted);
    margin-bottom: 0.25rem;
}

.cabin-value {
    font-size: 1.25rem;
    font-weight: 800;
    color: var(--cabin-text);
}

.cabin-section-title {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--cabin-muted);
    margin: 1rem 0 0.5rem;
}

.pill {
    display: inline-block;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.02em;
}
.pill-green { background: rgba(34,197,94,0.15); color: var(--cabin-green); border: 1px solid rgba(34,197,94,0.3); }
.pill-amber { background: rgba(245,158,11,0.15); color: var(--cabin-amber); border: 1px solid rgba(245,158,11,0.3); }
.pill-red   { background: rgba(239,68,68,0.15); color: var(--cabin-red); border: 1px solid rgba(239,68,68,0.3); }
.pill-blue  { background: rgba(59,130,246,0.15); color: var(--cabin-blue); border: 1px solid rgba(59,130,246,0.3); }
.pill-orange { background: rgba(249,115,22,0.15); color: var(--cabin-orange); border: 1px solid rgba(249,115,22,0.3); }

.bottom-nav {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: var(--cabin-card);
    border-top: 1px solid var(--cabin-border);
    display: flex;
    justify-content: space-around;
    padding: 0.5rem 0 calc(env(safe-area-inset-bottom, 0.5rem));
    z-index: 100;
}
.bottom-nav-item {
    flex: 1;
    text-align: center;
    font-size: 0.65rem;
    font-weight: 700;
    color: var(--cabin-muted);
    background: none;
    border: none;
    padding: 0.4rem 0;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.bottom-nav-item.active {
    color: var(--cabin-orange);
}
.bottom-nav-icon {
    font-size: 1.4rem;
    display: block;
    margin-bottom: 0.15rem;
}
</style>
"""


def apply_cabin_mode():
    st.markdown(CABIN_CSS, unsafe_allow_html=True)


def bottom_nav(active: str):
    items = [
        ("home", "Home", "🏠"),
        ("load", "Load", "📋"),
        ("hos", "HOS", "⏱️"),
        ("route", "Route", "🗺️"),
        ("more", "More", "☰"),
    ]
    cols = st.columns(len(items))
    for col, (key, label, icon) in zip(cols, items):
        with col:
            is_active = active == key
            st.markdown(
                f"<button class='bottom-nav-item {'active' if is_active else ''}' "
                f"onclick=\"document.getElementById('nav_{key}').click()\">"
                f"<span class='bottom-nav-icon'>{icon}</span>{label}</button>",
                unsafe_allow_html=True,
            )
            st.button(" ", key=f"nav_{key}", use_container_width=True)


def render_status_cards():
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Drive Left", "7.5h", delta="HOS")
    with col2:
        st.metric("ETA", "2:45 PM", delta="Kohler")
    with col3:
        st.metric("Load $", "$1,152", delta="Feldspar")


def render_current_load(load: dict[str, Any]):
    st.markdown('<div class="cabin-card">', unsafe_allow_html=True)
    st.markdown(f"<div class='cabin-label'>Current Load</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='cabin-value'>{load.get('bol_number', '—')}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='color:var(--cabin-muted);font-size:0.9rem;margin-top:0.25rem;'>"
        f"{load.get('shipper', '—')} · {load.get('commodity', '—')} · {load.get('weight_tons', 0)}t<br>"
        f"{load.get('origin', '—')} → {load.get('destination', '—')}"
        f"</div>",
        unsafe_allow_html=True,
    )
    status = load.get("status", "In Transit")
    color = {"In Transit": "blue", "Delivered": "green", "Scheduled": "amber"}.get(status, "blue")
    st.markdown(f"<div style='margin-top:0.5rem'><span class='pill pill-{color}'>{status}</span></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_hos(client: ELDClient | None = None):
    st.markdown('<div class="cabin-section-title">⏱️ Hours of Service</div>', unsafe_allow_html=True)
    if client is None:
        try:
            client = ELDClient()
        except Exception:
            client = None
    hos_data = {
        "drive_remaining": "7.5h",
        "on_duty_remaining": "10.5h",
        "cycle_remaining": "38.0h",
        "hours_today": "3.5h",
        "hours_week": "22.0h",
    }
    if client:
        try:
            hos = client.get_driver_hos("driver-1")
            hos_data = {
                "drive_remaining": f"{hos.drive_remaining_hours:.1f}h",
                "on_duty_remaining": f"{hos.on_duty_remaining_hours:.1f}h",
                "cycle_remaining": f"{hos.cycle_remaining_hours:.1f}h",
                "hours_today": f"{hos.hours_today:.1f}h",
                "hours_week": f"{hos.hours_week:.1f}h",
            }
        except Exception:
            pass
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Drive Left", hos_data["drive_remaining"])
    with c2:
        st.metric("On-Duty Left", hos_data["on_duty_remaining"])
    with c3:
        st.metric("Cycle Left", hos_data["cycle_remaining"])
    c4, c5 = st.columns(2)
    with c4:
        st.metric("Today", hos_data["hours_today"])
    with c5:
        st.metric("Week", hos_data["hours_week"])


def render_billing_card(load: dict[str, Any]):
    st.markdown('<div class="cabin-section-title">💰 This Load</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Revenue", f"${load.get('total_revenue', 0):,.2f}")
    with c2:
        st.metric("Rate", f"${load.get('rate_per_ton', 0):.2f}/t")
    st.metric("Miles", f"{load.get('loaded_miles', 0) + load.get('empty_miles', 0):.0f} total")


def render_route_map_stub():
    st.markdown('<div class="cabin-section-title">🗺️ Route</div>', unsafe_allow_html=True)
    st.markdown(
        "<div class='cabin-card-2' style='height:180px;display:flex;align-items:center;justify-content:center;"
        "background:linear-gradient(180deg,#0f172a 0%,#1e293b 100%);border-radius:14px;'>"
        "<div style='text-align:center;color:#94a3b8;'>"
        "<div style='font-size:2rem;'>📍</div>"
        "<div style='font-weight:700;color:#e2e8f0;'>Spruce Pine, NC</div>"
        "<div style='font-size:2rem;margin:0.5rem 0;'>➜</div>"
        "<div style='font-weight:700;color:#e2e8f0;'>Kohler, GA</div>"
        f"<div style='font-size:0.8rem;margin-top:0.5rem;'>Loaded {CURRENT_LOAD.get('loaded_miles', 285)} mi · "
        f"Empty {CURRENT_LOAD.get('empty_miles', 285)} mi</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )


def home_screen():
    st.markdown('<div class="cabin-section-title">📊 Status</div>', unsafe_allow_html=True)
    render_status_cards()
    render_current_load(CURRENT_LOAD)
    render_billing_card(CURRENT_LOAD)
    if st.button("ACK BOL", type="primary", use_container_width=True):
        st.success("BOL accepted — dispatch notified.")
    st.markdown('<div class="cabin-section-title">📍 Location</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Lat", f"{35.912:.4f}")
    with c2:
        st.metric("Lon", f"{-82.064:.4f}")


def load_screen():
    st.markdown('<div class="cabin-section-title">📋 Load</div>', unsafe_allow_html=True)
    render_current_load(CURRENT_LOAD)
    render_billing_card(CURRENT_LOAD)
    with st.form("update_load"):
        st.markdown('<div class="cabin-section-title">Update Status</div>', unsafe_allow_html=True)
        new_status = st.selectbox("Status", ["Scheduled", "In Transit", "Delivered", "Cancelled"], index=1)
        notes = st.text_area("Notes")
        if st.form_submit_button("Save Update", use_container_width=True):
            st.success("Load updated.")
            st.rerun()


def hos_screen():
    st.markdown('<div class="cabin-section-title">⏱️ HOS / ELD</div>', unsafe_allow_html=True)
    client = None
    try:
        from eld_integration import ELDClient
        client = ELDClient()
    except Exception:
        pass
    render_hos(client)
    if client:
        try:
            loc = client.get_vehicle_location("TRUCK-1")
            st.markdown(
                f"<div class='cabin-card-2'>"
                f"<div class='cabin-label'>GPS</div>"
                f"<div class='cabin-value'>{loc.lat:.4f}, {loc.lon:.4f}</div>"
                f"<div style='color:var(--cabin-muted);font-size:0.85rem;'>"
                f"{loc.speed_mph:.0f} mph · {loc.heading_deg:.0f}°</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        except Exception:
            pass


def route_screen():
    st.markdown('<div class="cabin-section-title">🗺️ Route & Tracking</div>', unsafe_allow_html=True)
    render_route_map_stub()
    routes_df = fetch_routes(load_id=1) if "fetch_routes" in globals() else pd.DataFrame()
    if not routes_df.empty:
        rrow = routes_df.iloc[0]
        loaded = rrow.get("planned_loaded_miles") or CURRENT_LOAD.get("loaded_miles", 285)
        empty = rrow.get("planned_empty_miles") or CURRENT_LOAD.get("empty_miles", 285)
        google = rrow.get("google_miles")
        actual_l = rrow.get("actual_loaded_miles")
        actual_e = rrow.get("actual_empty_miles")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Planned", f"{loaded + empty:.0f} mi")
        with c2:
            if google:
                st.metric("Google", f"{google:.0f} mi")
        if actual_l is not None and actual_e is not None:
            st.metric("Actual", f"{actual_l + actual_e:.0f} mi")


def more_screen():
    st.markdown('<div class="cabin-section-title">☰ More</div>', unsafe_allow_html=True)
    if st.button("📄 Generate BOL", use_container_width=True):
        st.session_state["show_bol"] = True
    if st.session_state.get("show_bol"):
        with st.form("bol_form"):
            ship = st.text_input("Shipper", value=CURRENT_LOAD.get("shipper", ""))
            com = st.text_input("Commodity", value=CURRENT_LOAD.get("commodity", ""))
            wt = st.number_input("Weight (tons)", value=float(CURRENT_LOAD.get("weight_tons", 22)))
            rt = st.number_input("Rate per Ton", value=float(CURRENT_LOAD.get("rate_per_ton", 55)))
            if st.form_submit_button("Generate"):
                bol_text = (
                    f"L & P FREIGHT — BILL OF LADING\n"
                    f"Date: {date.today()}\n"
                    f"BOL #: {CURRENT_LOAD.get('bol_number')}\n"
                    f"SHIPPER: {ship}\n"
                    f"COMMODITY: {com}\n"
                    f"WEIGHT: {wt} tons\n"
                    f"RATE: ${rt:.2f}/ton\n"
                    f"TOTAL: ${wt*rt:.2f}\n"
                    f"ORIGIN: Spruce Pine, NC\n"
                    f"DESTINATION: Central Georgia (Kohler)\n"
                    f"TRAILER: 39 ft Frameless End-Dump"
                )
                st.code(bol_text)
                st.download_button("Download BOL", bol_text, file_name="BOL.txt", use_container_width=True)
    st.divider()
    if st.button("📊 Settlement", use_container_width=True):
        st.info("Settlement history available in dispatch app.")
    if st.button("⚙️ Settings", use_container_width=True):
        st.info("Night mode: ON. Cabin mode: ON. Touch targets: 52px.")


def main():
    apply_cabin_mode()

    if "mobile_page" not in st.session_state:
        st.session_state.mobile_page = "home"

    def navigate(page):
        st.session_state.mobile_page = page
        st.rerun()

    page = st.session_state.get("mobile_page", "home")

    if page == "home":
        home_screen()
    elif page == "load":
        load_screen()
    elif page == "hos":
        hos_screen()
    elif page == "route":
        route_screen()
    elif page == "more":
        more_screen()

    bottom_nav(page)


if __name__ == "__main__":
    main()
