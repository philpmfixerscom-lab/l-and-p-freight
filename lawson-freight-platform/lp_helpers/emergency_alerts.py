"""Emergency dispatch buttons — truck, load, medical, roadside SOS for L & P Lawson."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import streamlit as st

EMERGENCY_TYPES: dict[str, dict[str, str]] = {
    "medical": {
        "label": "Medical Emergency",
        "icon": "🚨",
        "short": "MEDICAL",
        "severity": "critical",
    },
    "truck_breakdown": {
        "label": "Truck Malfunction",
        "icon": "🔧",
        "short": "TRUCK DOWN",
        "severity": "high",
    },
    "load_issue": {
        "label": "Load Issue",
        "icon": "📦",
        "short": "LOAD ISSUE",
        "severity": "high",
    },
    "roadside_sos": {
        "label": "Roadside SOS",
        "icon": "🆘",
        "short": "SOS",
        "severity": "critical",
    },
}

EMERGENCY_SMS_TEMPLATE = (
    "🚨 L & P EMERGENCY | {short}\n"
    "Driver: {driver}\n"
    "Unit: {truck_label}\n"
    "BOL: {bol_number}\n"
    "Load: {commodity} · {weight_tons:.1f}t\n"
    "Route: {origin} → {destination}\n"
    "GPS: {gps_text}\n"
    "Detail: {detail}\n"
    "Time: {timestamp}\n"
    "— Phillip / Lawson Dispatch"
)


def format_emergency_message(context: dict[str, Any]) -> str:
    defaults: dict[str, Any] = {
        "short": "EMERGENCY",
        "driver": "Driver",
        "truck_label": "L&P End-Dump",
        "bol_number": "—",
        "commodity": "—",
        "weight_tons": 0.0,
        "origin": "Spruce Pine, NC",
        "destination": "Central GA",
        "gps_text": "Location unknown",
        "detail": "Assistance needed",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    defaults.update(context)
    try:
        return EMERGENCY_SMS_TEMPLATE.format(**defaults)
    except (KeyError, ValueError):
        return (
            f"L & P EMERGENCY — {defaults.get('short')} — "
            f"{defaults.get('driver')} — {defaults.get('detail')}"
        )


def build_emergency_context(
    emergency_key: str,
    *,
    driver: str,
    truck_label: str,
    load: dict[str, Any] | None = None,
    gps_fix: dict[str, Any] | None = None,
    detail: str = "",
) -> dict[str, Any]:
    meta = EMERGENCY_TYPES.get(emergency_key, EMERGENCY_TYPES["roadside_sos"])
    load = load or {}
    if gps_fix and gps_fix.get("latitude") is not None:
        gps_text = (
            f"{gps_fix['latitude']:.5f}, {gps_fix['longitude']:.5f} "
            f"({gps_fix.get('speed_mph', 0):.0f} mph)"
        )
    else:
        gps_text = "GPS unavailable — check Traccar or call driver"

    default_details = {
        "medical": "Driver needs immediate medical assistance.",
        "truck_breakdown": "Truck/trailer mechanical failure — roadside assistance needed.",
        "load_issue": "Load problem — shift, spill, scale, or shipper/receiver issue.",
        "roadside_sos": "General roadside emergency — driver requests immediate dispatch contact.",
    }
    return {
        "short": meta["short"],
        "driver": driver,
        "truck_label": truck_label,
        "bol_number": load.get("bol_number", "—"),
        "commodity": load.get("commodity", "—"),
        "weight_tons": float(load.get("weight_tons", 0) or 0),
        "origin": load.get("origin", "Spruce Pine, NC"),
        "destination": load.get("destination", "Central GA"),
        "gps_text": gps_text,
        "detail": detail.strip() or default_details.get(emergency_key, "Emergency"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _emergency_css(compact: bool = False) -> str:
    pad = "0.65rem" if compact else "0.85rem"
    return f"""
    <style>
    .lf-emergency-banner {{
        background: linear-gradient(135deg, #7f1d1d 0%, #991b1b 50%, #b45309 100%);
        border: 2px solid #fca5a5;
        border-radius: 14px;
        padding: {pad} 1rem;
        margin-bottom: 0.75rem;
        color: #fff;
    }}
    .lf-emergency-banner h4 {{ margin: 0 0 0.25rem; font-size: 1rem; font-weight: 800; }}
    .lf-emergency-banner p {{ margin: 0; font-size: 0.8rem; opacity: 0.92; }}
    div[data-testid="stVerticalBlock"]:has(.lf-emergency-marker) .stButton > button {{
        min-height: 56px !important;
        font-weight: 800 !important;
        border-radius: 12px !important;
    }}
    </style>
    """


def render_emergency_panel(
    *,
    driver: str,
    truck_label: str,
    load: dict[str, Any] | None,
    gps_fix: dict[str, Any] | None,
    on_dispatch: Callable[[str, str, dict[str, Any]], tuple[bool, str]],
    compact: bool = False,
    key_prefix: str = "emergency",
) -> None:
    """
    Render emergency buttons with confirm step.
    on_dispatch(emergency_key, message, context) -> (sent_ok, status_message)
    """
    st.markdown(_emergency_css(compact), unsafe_allow_html=True)
    st.markdown(
        '<div class="lf-emergency-banner">'
        "<h4>🚨 Emergency Dispatch</h4>"
        "<p>Truck down · load issue · medical · roadside SOS — logs alert &amp; texts dispatch if Twilio is on.</p>"
        "</div>"
        '<div class="lf-emergency-marker"></div>',
        unsafe_allow_html=True,
    )

    confirm_key = f"{key_prefix}_confirm"
    pending = st.session_state.get(confirm_key)

    if pending:
        meta = EMERGENCY_TYPES.get(pending, {})
        st.error(f"**Confirm {meta.get('label', pending)}?** This logs and may send SMS immediately.")
        detail = st.text_input(
            "Additional detail (optional)",
            placeholder="Mile marker, symptoms, load shift, etc.",
            key=f"{key_prefix}_detail_{pending}",
        )
        c1, c2 = st.columns(2)
        if c1.button("✅ CONFIRM — SEND", type="primary", use_container_width=True, key=f"{key_prefix}_yes"):
            ctx = build_emergency_context(
                pending,
                driver=driver,
                truck_label=truck_label,
                load=load,
                gps_fix=gps_fix,
                detail=detail,
            )
            msg = format_emergency_message(ctx)
            sent_ok, status = on_dispatch(pending, msg, ctx)
            st.session_state.pop(confirm_key, None)
            if sent_ok:
                st.success(status)
            else:
                st.warning(status)
            st.rerun()
        if c2.button("Cancel", use_container_width=True, key=f"{key_prefix}_no"):
            st.session_state.pop(confirm_key, None)
            st.rerun()
        return

    cols = st.columns(2)
    keys = list(EMERGENCY_TYPES.keys())
    for idx, ekey in enumerate(keys):
        meta = EMERGENCY_TYPES[ekey]
        with cols[idx % 2]:
            if st.button(
                f"{meta['icon']} {meta['label']}",
                use_container_width=True,
                key=f"{key_prefix}_btn_{ekey}",
                type="primary" if meta["severity"] == "critical" else "secondary",
            ):
                st.session_state[confirm_key] = ekey
                st.rerun()