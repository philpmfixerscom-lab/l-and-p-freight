"""Emergency dispatch — official 911 dial pad + L & P dispatch SMS alerts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable

import streamlit as st

# Official voice emergency lines — CALL these; do NOT SMS via Twilio
OFFICIAL_EMERGENCY_DIAL: list[dict[str, str]] = [
    {
        "id": "911",
        "label": "911",
        "tel": "911",
        "display": "911",
        "note": "Police · Fire · Ambulance — life-threatening emergencies",
        "priority": "critical",
    },
    {
        "id": "988",
        "label": "988 Crisis Line",
        "tel": "988",
        "display": "988",
        "note": "Suicide & mental health crisis (call or text)",
        "priority": "critical",
    },
    {
        "id": "nc_hp",
        "label": "NC Highway Patrol",
        "tel": "18006227956",
        "display": "*47 or 1-800-622-7956",
        "note": "NC interstates · Spruce Pine · I-26 · Hwy 19E",
        "priority": "high",
    },
    {
        "id": "ga_gsp",
        "label": "GA State Patrol",
        "tel": "*477",
        "display": "*477",
        "note": "Georgia interstates · Central GA / Kohler area",
        "priority": "high",
    },
    {
        "id": "road_511",
        "label": "511 Travel Info",
        "tel": "511",
        "display": "511",
        "note": "NC/GA road conditions · accidents · closures",
        "priority": "normal",
    },
    {
        "id": "hazmat",
        "label": "Hazmat Spill (NRC)",
        "tel": "18004248802",
        "display": "1-800-424-8802",
        "note": "National Response Center — chemical/spill emergencies",
        "priority": "high",
    },
]

# Numbers that must never receive Twilio SMS
SMS_BLOCKLIST_DIGITS = frozenset({
    "911", "988", "511", "447", "477", "47",
    "18006227956", "18004248802",
})

EMERGENCY_TYPES: dict[str, dict[str, Any]] = {
    "medical": {
        "label": "Medical Emergency",
        "icon": "🚨",
        "short": "MEDICAL",
        "severity": "critical",
        "call_first": "911",
        "also_dial": ["988"],
    },
    "truck_breakdown": {
        "label": "Truck Malfunction",
        "icon": "🔧",
        "short": "TRUCK DOWN",
        "severity": "high",
        "call_first": None,
        "also_dial": ["nc_hp", "ga_gsp", "road_511"],
    },
    "load_issue": {
        "label": "Load Issue",
        "icon": "📦",
        "short": "LOAD ISSUE",
        "severity": "high",
        "call_first": None,
        "also_dial": ["hazmat", "road_511"],
    },
    "roadside_sos": {
        "label": "Roadside SOS",
        "icon": "🆘",
        "short": "SOS",
        "severity": "critical",
        "call_first": "911",
        "also_dial": ["nc_hp", "ga_gsp"],
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
    "⚠️ Life-threatening: CALL 911 (not SMS)\n"
    "— Phillip / Lawson Dispatch"
)


def is_sms_blocked_number(phone: str) -> bool:
    """Prevent Twilio SMS to official emergency voice lines."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return True
    if digits in SMS_BLOCKLIST_DIGITS:
        return True
    if len(digits) <= 3:
        return True
    if digits.endswith("911") or digits.endswith("988"):
        return True
    for blocked in SMS_BLOCKLIST_DIGITS:
        if digits.endswith(blocked) and len(digits) <= len(blocked) + 1:
            return True
    return False


def _dial_by_id(dial_id: str) -> dict[str, str] | None:
    for entry in OFFICIAL_EMERGENCY_DIAL:
        if entry["id"] == dial_id:
            return entry
    return None


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
        "medical": "Driver needs immediate medical assistance — 911 called or requested.",
        "truck_breakdown": "Truck/trailer mechanical failure — roadside assistance needed.",
        "load_issue": "Load problem — shift, spill, scale, or shipper/receiver issue.",
        "roadside_sos": "General roadside emergency — driver requests immediate help.",
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
    .lf-dial-911 {{
        background: #dc2626 !important;
        border: 3px solid #fecaca !important;
        border-radius: 14px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        text-align: center;
    }}
    .lf-dial-911 a {{
        color: #fff !important;
        font-size: 1.75rem !important;
        font-weight: 900 !important;
        text-decoration: none !important;
    }}
    div[data-testid="stVerticalBlock"]:has(.lf-emergency-marker) .stButton > button {{
        min-height: 56px !important;
        font-weight: 800 !important;
        border-radius: 12px !important;
    }}
    </style>
    """


def render_official_dial_pad(
    *,
    key_prefix: str = "dial",
    highlight_ids: list[str] | None = None,
    compact: bool = False,
) -> None:
    """Tap-to-call official emergency numbers (911, highway patrol, etc.)."""
    st.markdown("##### 📞 Official Emergency Numbers")
    st.caption("Tap to call on your phone. **911 and 988 are voice/text crisis lines — not SMS.**")

    highlight_ids = highlight_ids or ["911"]
    priority = [d for d in OFFICIAL_EMERGENCY_DIAL if d["id"] in highlight_ids]
    rest = [d for d in OFFICIAL_EMERGENCY_DIAL if d["id"] not in highlight_ids]

    if any(d["id"] == "911" for d in priority):
        st.markdown(
            '<div class="lf-dial-911">'
            '<a href="tel:911">📞 CALL 911 NOW</a>'
            "<div style='font-size:0.8rem;margin-top:0.25rem;opacity:0.9'>"
            "Life-threatening medical · fire · crime in progress</div></div>",
            unsafe_allow_html=True,
        )

    show = priority + rest if not compact else priority + rest[:3]
    cols = st.columns(2)
    for idx, entry in enumerate(show):
        if entry["id"] == "911":
            continue
        with cols[idx % 2]:
            label = f"📞 {entry['label']}"
            st.link_button(
                label,
                f"tel:{entry['tel']}",
                use_container_width=True,
                help=entry["note"],
                type="primary" if entry.get("priority") == "critical" else "secondary",
            )
            st.caption(f"{entry['display']} — {entry['note']}")


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
    """Official dial pad + L & P dispatch SMS buttons (confirm step)."""
    st.markdown(_emergency_css(compact), unsafe_allow_html=True)
    st.markdown(
        '<div class="lf-emergency-banner">'
        "<h4>🚨 Emergency</h4>"
        "<p><b>Step 1:</b> Call 911 / Highway Patrol below if needed. "
        "<b>Step 2:</b> Alert Phillip &amp; Lawson dispatch (SMS).</p>"
        "</div>"
        '<div class="lf-emergency-marker"></div>',
        unsafe_allow_html=True,
    )

    render_official_dial_pad(key_prefix=f"{key_prefix}_dial", compact=compact)

    st.markdown("##### 📲 Alert L & P Dispatch")
    st.caption("Texts Phillip/Lawson — does **not** replace calling 911.")

    confirm_key = f"{key_prefix}_confirm"
    pending = st.session_state.get(confirm_key)

    if pending:
        meta = EMERGENCY_TYPES.get(pending, {})
        call_first = meta.get("call_first")
        if call_first:
            dial = _dial_by_id(call_first)
            if dial:
                st.error(
                    f"**If this is life-threatening, call {dial['display']} FIRST** "
                    "before or while alerting dispatch."
                )
                st.link_button(
                    f"📞 CALL {dial['display']} NOW",
                    f"tel:{dial['tel']}",
                    type="primary",
                    use_container_width=True,
                )
        for extra_id in meta.get("also_dial", []):
            extra = _dial_by_id(extra_id)
            if extra and extra["id"] != call_first:
                st.link_button(
                    f"📞 {extra['label']} ({extra['display']})",
                    f"tel:{extra['tel']}",
                    use_container_width=True,
                    help=extra["note"],
                )

        st.warning(
            f"Confirm **{meta.get('label', pending)}** dispatch alert? "
            "This logs the event and texts your L & P contacts."
        )
        detail = st.text_input(
            "Additional detail (optional)",
            placeholder="Mile marker, symptoms, load shift, etc.",
            key=f"{key_prefix}_detail_{pending}",
        )
        c1, c2 = st.columns(2)
        if c1.button("✅ Alert Dispatch", type="primary", use_container_width=True, key=f"{key_prefix}_yes"):
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