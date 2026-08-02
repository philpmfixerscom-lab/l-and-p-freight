"""Mobile driver cabin UI — touch-friendly, DB-backed, Traccar GPS for Phillip / Lawson."""

from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
from typing import Any, Callable

import streamlit as st

CABIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
:root {
    --cabin-bg: #0b0f14; --cabin-card: #141a22; --cabin-text: #f1f5f9;
    --cabin-muted: #94a3b8; --cabin-border: #3d4b5f; --cabin-orange: #f97316;
    --cabin-orange-soft: rgba(249, 115, 22, 0.12);
    --cabin-danger: #ef4444; --cabin-green: #22c55e; --cabin-blue: #38bdf8;
}
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, sans-serif !important;
    background: var(--cabin-bg) !important; color: var(--cabin-text) !important;
    font-size: 17px !important;
}
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { padding: 0.75rem 1rem 5.5rem !important; max-width: 480px !important; }

/* ── Buttons: outline-first cabin chrome (orange is accent, not flood fill) ── */
.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button,
.stLinkButton > a,
div[data-testid="stLinkButton"] > a {
    min-height: 56px !important;
    font-weight: 700 !important;
    font-size: 1.02rem !important;
    border-radius: 14px !important;
    background: transparent !important;
    color: var(--cabin-text) !important;
    border: 2px solid var(--cabin-border) !important;
    box-shadow: none !important;
    transition: background 0.12s, border-color 0.12s, color 0.12s;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover,
.stLinkButton > a:hover,
div[data-testid="stLinkButton"] > a:hover {
    background: rgba(255,255,255,0.04) !important;
    border-color: #64748b !important;
}
.stButton > button:active,
.stLinkButton > a:active {
    transform: scale(0.98);
}
/* Primary = orange outline + soft tint (not solid fill) */
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
    background: var(--cabin-orange-soft) !important;
    color: #fdba74 !important;
    border: 2px solid var(--cabin-orange) !important;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    background: rgba(249, 115, 22, 0.2) !important;
    color: #fed7aa !important;
}
/* Secondary = neutral outline */
.stButton > button[kind="secondary"],
.stFormSubmitButton > button[kind="secondary"] {
    background: transparent !important;
    color: var(--cabin-text) !important;
    border: 2px solid var(--cabin-border) !important;
}
/* Map / dial link buttons — blue outline (nav) so orange is not everywhere */
.stLinkButton > a,
div[data-testid="stLinkButton"] > a {
    background: rgba(56, 189, 248, 0.08) !important;
    color: #7dd3fc !important;
    border: 2px solid rgba(56, 189, 248, 0.55) !important;
}
.stLinkButton > a:hover,
div[data-testid="stLinkButton"] > a:hover {
    background: rgba(56, 189, 248, 0.16) !important;
    border-color: var(--cabin-blue) !important;
    color: #e0f2fe !important;
}
.stButton > button:disabled {
    opacity: 0.45 !important;
    border-style: dashed !important;
}

.cabin-card {
    background: var(--cabin-card); border: 1px solid var(--cabin-border);
    border-radius: 16px; padding: 1rem; margin-bottom: 0.75rem;
}
.cabin-next {
    background: rgba(148, 163, 184, 0.08);
    border: 1px solid var(--cabin-border);
    border-left: 4px solid var(--cabin-orange);
    border-radius: 14px; padding: 0.85rem 1rem; margin-bottom: 0.75rem;
    font-weight: 600; font-size: 1.02rem; color: var(--cabin-text);
}
.cabin-nav-card {
    background: rgba(20, 26, 34, 0.98);
    border: 1px solid var(--cabin-border);
    border-left: 4px solid var(--cabin-blue);
    border-radius: 14px;
    padding: 1rem 1.1rem;
    margin-bottom: 0.75rem;
}
.pill { display:inline-block; padding:0.45rem 0.95rem; border-radius:999px;
    font-size:0.9rem; font-weight:700; border: 1px solid transparent; }
.pill-blue { background:rgba(59,130,246,0.18); color:#93c5fd; border-color:rgba(59,130,246,0.35); }
.pill-green { background:rgba(34,197,94,0.18); color:#4ade80; border-color:rgba(34,197,94,0.35); }
.pill-amber { background:rgba(251,191,36,0.18); color:#fbbf24; border-color:rgba(251,191,36,0.35); }
.stTextInput input, .stTextArea textarea, .stSelectbox > div > div {
    min-height: 48px !important; font-size: 1.05rem !important;
    color: #f1f5f9 !important; background: #1e2937 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
    border: 1px solid var(--cabin-border) !important;
}
/* Bin estimate radios — large cabin touch targets */
div[role="radiogroup"] label {
    min-height: 48px !important; padding: 0.55rem 0.65rem !important;
    font-size: 1.02rem !important; margin-bottom: 0.35rem !important;
    border: 1px solid var(--cabin-border) !important; border-radius: 10px !important;
}
div[data-testid="stNumberInput"] input {
    min-height: 48px !important; font-size: 1.1rem !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.45rem !important; font-weight: 800 !important; color: #bae6fd !important;
}
</style>
"""

CABIN_CSS_DAY = """
<style>
:root {
    --cabin-bg: #f1f5f9; --cabin-card: #ffffff; --cabin-text: #0f172a;
    --cabin-muted: #475569; --cabin-border: #94a3b8; --cabin-orange: #ea580c;
    --cabin-orange-soft: rgba(234, 88, 12, 0.08);
    --cabin-danger: #dc2626; --cabin-green: #16a34a; --cabin-blue: #0284c7;
}
html, body, [class*="css"] {
    background: var(--cabin-bg) !important; color: var(--cabin-text) !important;
}
.cabin-card { background: var(--cabin-card); border-color: var(--cabin-border); }
.cabin-next {
    background: #fff;
    border: 1px solid var(--cabin-border);
    border-left: 4px solid var(--cabin-orange);
    color: var(--cabin-text);
}
.cabin-nav-card {
    background: #fff;
    border: 1px solid var(--cabin-border);
    border-left: 4px solid var(--cabin-blue);
}
.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button,
.stLinkButton > a,
div[data-testid="stLinkButton"] > a {
    background: #fff !important;
    color: var(--cabin-text) !important;
    border: 2px solid var(--cabin-border) !important;
}
.stButton > button:hover,
.stLinkButton > a:hover,
div[data-testid="stLinkButton"] > a:hover {
    background: #f8fafc !important;
    border-color: #64748b !important;
}
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background: var(--cabin-orange-soft) !important;
    color: #c2410c !important;
    border: 2px solid var(--cabin-orange) !important;
}
.stButton > button[kind="secondary"] {
    background: #fff !important;
    color: var(--cabin-text) !important;
    border: 2px solid var(--cabin-border) !important;
}
.stLinkButton > a,
div[data-testid="stLinkButton"] > a {
    background: rgba(2, 132, 199, 0.06) !important;
    color: #0369a1 !important;
    border: 2px solid rgba(2, 132, 199, 0.45) !important;
}
.stTextInput input, .stTextArea textarea, .stSelectbox > div > div {
    color: #0f172a !important; background: #f8fafc !important;
    -webkit-text-fill-color: #0f172a !important;
    border: 1px solid var(--cabin-border) !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #0c4a6e !important;
}
div[role="radiogroup"] label {
    border: 1px solid var(--cabin-border) !important; border-radius: 10px !important;
}
</style>
"""

# One-tap status flow for plant / road work
STATUS_ACTIONS: tuple[tuple[str, str, str], ...] = (
    ("I'm on site", "Arrived", "driver_act_onsite"),
    ("Loaded / rolling", "In Transit", "driver_act_rolling"),
    ("Delivered", "Delivered", "driver_act_delivered"),
)


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def get_navigation_links(
    origin: str = "Spruce Pine, NC",
    destination: str = "Central Georgia Kohler area",
) -> tuple[str, str]:
    """Return Google Maps and Apple Maps deep-link URLs (dependency-free)."""
    from urllib.parse import quote_plus

    origin_q = quote_plus(origin)
    dest_q = quote_plus(destination)
    google = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin_q}&destination={dest_q}&travelmode=driving"
    )
    apple = f"https://maps.apple.com/?saddr={origin_q}&daddr={dest_q}&dirflg=d"
    return google, apple


def _render_nav_link_button(label: str, url: str) -> None:
    """Prefer st.link_button; outlined markdown fallback for older Streamlit."""
    if hasattr(st, "link_button"):
        st.link_button(label, url, use_container_width=True)
        return
    st.markdown(
        f"""
        <a href="{url}" target="_blank" rel="noopener noreferrer" style="
            display:flex; align-items:center; justify-content:center; text-align:center;
            text-decoration:none; background: rgba(56, 189, 248, 0.08);
            color:#7dd3fc; border:2px solid rgba(56, 189, 248, 0.55);
            border-radius:14px; padding:0.95rem 0.75rem;
            margin-bottom:0.4rem; font-weight:700; font-size:1.05rem;
            min-height:56px; box-sizing:border-box;
        ">{label}</a>
        """,
        unsafe_allow_html=True,
    )


def render_primary_navigation_card(
    *,
    origin_label: str = "Spruce Pine, NC (Sibelco / Covia / K-T area)",
    destination_label: str = "Central Georgia – Kohler area / as directed",
    origin_query: str = "Spruce Pine, NC",
    destination_query: str = "Central Georgia Kohler area",
) -> None:
    """Primary cab GPS — large one-tap native maps (preferred over interactive map)."""
    st.markdown("#### 🗺️ Navigation")
    st.markdown(
        f"""
<div class="cabin-nav-card">
    <div style="font-size: 0.75rem; color: var(--cabin-muted); letter-spacing: 0.5px; margin-bottom: 0.2rem;">ORIGIN</div>
    <div style="font-size: 1.1rem; font-weight: 700; color: var(--cabin-text); margin-bottom: 0.75rem;">
        {origin_label}
    </div>
    <div style="font-size: 0.75rem; color: var(--cabin-muted); letter-spacing: 0.5px; margin-bottom: 0.2rem;">DESTINATION</div>
    <div style="font-size: 1.1rem; font-weight: 700; color: var(--cabin-text); margin-bottom: 0.55rem;">
        {destination_label}
    </div>
    <div style="font-size: 0.8rem; color: var(--cabin-blue);">
        Lane: Spruce Pine NC → Central GA · ~275 miles · Ready for navigation
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )
    google_url, apple_url = get_navigation_links(origin_query, destination_query)
    b1, b2 = st.columns(2)
    with b1:
        _render_nav_link_button("🗺️ Open in Google Maps", google_url)
    with b2:
        _render_nav_link_button("🍎 Open in Apple Maps", apple_url)


def fetch_active_load(get_connection: Callable[[], Any]) -> dict[str, Any]:
    try:
        from lp_helpers.repositories.loads import fetch_active_load_row

        with closing(get_connection()) as conn:
            row = fetch_active_load_row(conn)
        if row is None:
            return _default_load()
        return row
    except Exception:
        try:
            with closing(get_connection()) as conn:
                row = conn.execute(
                    """
                    SELECT * FROM loads
                    WHERE status IN ('Dispatched', 'In Transit', 'Booked', 'Arrived', 'Loaded')
                    ORDER BY pickup_date DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()
            if row is None:
                return _default_load()
            return {k: row[k] for k in row.keys()}
        except Exception:
            return _default_load()


def _next_action_blurb(status: str, load: dict[str, Any]) -> str:
    dest = str(load.get("destination") or "receiver")
    origin = str(load.get("origin") or "shipper")
    s = status.lower()
    if s in ("available", "—", ""):
        return "Next: wait for dispatch or log a load in Dispatch."
    if s in ("booked", "quoted", "potential"):
        return f"Next: head to pickup · {origin}"
    if s == "dispatched":
        return f"Next: arrive on site · {origin}"
    if s in ("arrived", "on site"):
        return f"Next: load & scale · then roll to {dest}"
    if s in ("loaded", "in transit"):
        return f"Next: deliver · {dest}"
    if s == "delivered":
        return "Next: find a return home — open Dispatch deadhead panel."
    return f"Status: {status} · stay safe"


def _next_status_key(status: str) -> str | None:
    """Which STATUS_ACTIONS key is the next step (gets orange outline only)."""
    s = status.lower()
    if s in ("available", "—", "", "booked", "quoted", "potential", "dispatched"):
        return "driver_act_onsite"
    if s in ("arrived", "on site"):
        return "driver_act_rolling"
    if s in ("loaded", "in transit"):
        return "driver_act_delivered"
    return None


def _pill_class(status: str) -> str:
    s = status.lower()
    if s in ("in transit", "dispatched", "loaded"):
        return "pill-blue"
    if s in ("delivered", "complete", "completed"):
        return "pill-green"
    if s in ("arrived", "booked"):
        return "pill-amber"
    return "pill-green"


def _update_load_status(
    get_connection: Callable[[], Any],
    load_id: Any,
    new_status: str,
    owner: str,
    note: str = "",
) -> tuple[bool, str]:
    if not load_id:
        return False, "Log a load in dispatch first."
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    extra = f"\n[{stamp} {owner}] {note or new_status}"
    try:
        with closing(get_connection()) as conn:
            conn.execute(
                """
                UPDATE loads SET status = ?,
                    notes = COALESCE(notes, '') || ?
                WHERE id = ?
                """,
                (new_status, extra, load_id),
            )
            conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        return True, new_status
    except Exception as exc:
        return False, str(exc)


def render_driver_app(
    *,
    get_connection: Callable[[], Any],
    get_active_owner: Callable[[], str],
    truck_label: str,
    get_traccar_status: Callable[[], dict[str, Any] | None] | None = None,
    format_sms: Callable[[str, dict[str, Any]], str] | None = None,
    log_sms_event: Callable[..., None] | None = None,
    try_send_sms: Callable[..., tuple[bool, str]] | None = None,
    on_emergency: Callable[[str, str, dict[str, Any]], tuple[bool, str]] | None = None,
    on_exit: Callable[[], None] | None = None,
    **_ignored: Any,
) -> None:
    """Cab UI — single scroll, large CTAs, DB-backed status. Signature-tolerant."""
    if get_traccar_status is None:
        get_traccar_status = lambda: None  # noqa: E731
    if format_sms is None:

        def format_sms(_key: str, ctx: dict[str, Any]) -> str:
            return (
                f"L & P FREIGHT | {ctx.get('company', 'Dispatch')} | "
                f"{ctx.get('location', 'Site')}"
            )

    if log_sms_event is None:
        log_sms_event = lambda *_a, **_k: None  # noqa: E731

    night = bool(st.session_state.get("night_mode", True))
    st.markdown(CABIN_CSS, unsafe_allow_html=True)
    if not night:
        st.markdown(CABIN_CSS_DAY, unsafe_allow_html=True)

    owner = str(get_active_owner() or "Driver")
    load = fetch_active_load(get_connection)
    status = str(load.get("status", "Available"))
    load_id = load.get("id")

    top1, top2 = st.columns([3, 1])
    with top1:
        st.markdown("## L & P Driver")
        st.caption(f"{owner} · {truck_label} · Cab mode")
    with top2:
        if st.button(
            "Exit",
            use_container_width=True,
            type="secondary",
            key="driver_exit_btn",
        ):
            if on_exit:
                on_exit()
            st.rerun()

    # Emergency first — always reachable
    try:
        fix = get_traccar_status()
    except Exception:
        fix = None

    if on_emergency:
        try:
            from lp_helpers.emergency_alerts import render_emergency_panel

            render_emergency_panel(
                driver=owner,
                truck_label=truck_label,
                load=load,
                gps_fix=fix,
                on_dispatch=on_emergency,
                compact=True,
                key_prefix="driver_em",
            )
        except Exception as exc:
            st.warning(f"Emergency panel unavailable: {exc}")

    # ── Log Bin Estimate (Phase 1 field gap) — always available at silo ──
    st.markdown("#### Bin inventory")
    show_bin = bool(st.session_state.get("driver_show_bin_est"))
    bin_btn_label = "▼ Hide Bin Estimate" if show_bin else "🗑️ Log Bin Estimate"
    if st.button(
        bin_btn_label,
        use_container_width=True,
        type="secondary",
        key="driver_bin_est_btn",
    ):
        st.session_state.driver_show_bin_est = not show_bin
        st.rerun()
    if st.session_state.get("driver_show_bin_est"):
        _render_bin_estimate(get_connection, load, owner)

    # Primary GPS for drivers — one-tap native turn-by-turn (cab-first, no map library)
    render_primary_navigation_card()

    # Load card
    st.markdown('<div class="cabin-card">', unsafe_allow_html=True)
    st.markdown(f"**{load.get('bol_number', '—')}**")
    st.caption(
        f"{load.get('shipper', '—')} · {load.get('commodity', '—')} · "
        f"{load.get('weight_tons', 0)}t"
    )
    st.caption(f"{load.get('origin', '—')} → {load.get('destination', '—')}")
    pill = _pill_class(status)
    st.markdown(f"<span class='pill {pill}'>{status}</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Next action (ops over revenue)
    st.markdown(
        f'<div class="cabin-next">{_next_action_blurb(status, load)}</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    c1.metric("Miles", f"{_safe_float(load.get('loaded_miles'), 285):.0f} ld")
    c2.metric("Rate", f"${_safe_float(load.get('rate_per_ton')):.2f}/t")

    # Status actions — outlined stack; only the next step is orange-outline primary
    st.markdown("#### Status")
    next_key = _next_status_key(status)
    for label, new_status, key in STATUS_ACTIONS:
        is_current = status.lower() == new_status.lower()
        is_next = key == next_key
        if st.button(
            f"{'✓ ' if is_current else ''}{label}",
            use_container_width=True,
            type="primary" if is_next and not is_current else "secondary",
            key=key,
            disabled=is_current and bool(load_id),
        ):
            ok, msg = _update_load_status(
                get_connection, load_id, new_status, owner, note=label
            )
            if ok:
                # After deliver, stash empty location for deadhead panel
                if new_status == "Delivered":
                    dest = str(load.get("destination") or "")
                    if dest:
                        st.session_state["dh_empty_at"] = dest
                st.success(f"Status → {msg}")
                st.rerun()
            else:
                st.warning(msg)

    # Notes (optional)
    with st.expander("Add note", expanded=False):
        note = st.text_area(
            "Driver notes",
            placeholder="Scale ticket, gate time, delay…",
            key="driver_note_text",
        )
        if st.button(
            "Save note",
            use_container_width=True,
            type="secondary",
            key="driver_save_note",
        ):
            if load_id and note.strip():
                ok, msg = _update_load_status(
                    get_connection, load_id, status, owner, note=note.strip()
                )
                if ok:
                    st.success("Note saved.")
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Enter a note and ensure a load is active.")

    # Live tracking (secondary) — Traccar status only; navigation is the card above
    st.markdown("#### Live tracking")
    st.caption("Fleet GPS status · use Navigation above for turn-by-turn")
    if fix and fix.get("latitude") is not None and fix.get("longitude") is not None:
        g1, g2 = st.columns(2)
        g1.metric("Speed", f"{_safe_float(fix.get('speed_mph')):.0f} mph")
        age = fix.get("last_update") or fix.get("device_name") or "live"
        g2.metric("Fix", str(age)[:18])
        st.caption(
            f"Live Traccar · {_safe_float(fix.get('latitude')):.4f}, "
            f"{_safe_float(fix.get('longitude')):.4f}"
        )
    else:
        st.info("Traccar offline — yard fallback (Spruce Pine).")
        y1, y2 = st.columns(2)
        y1.metric("Speed", "—")
        y2.metric("Fix", "offline")
        st.caption("35.9120, -82.0640 · Spruce Pine yard")

    # Arrival SMS (no nested tabs)
    with st.expander("Arrival alert", expanded=False):
        arrival_msg = format_sms(
            "arrival",
            {
                "company": load.get("shipper", "Dispatch"),
                "location": load.get("destination", "Site"),
                "driver": owner,
            },
        )
        st.text_area("Arrival SMS", arrival_msg, height=120, key="driver_arrival_preview")
        if st.button(
            "Log Arrival Alert",
            use_container_width=True,
            type="secondary",
            key="driver_arrival_log",
        ):
            if try_send_sms is not None:
                dispatch_phone = str(
                    st.session_state.get("twilio_dispatch_phone")
                    or st.session_state.get("dispatch_phone")
                    or ""
                ).strip()
                if not dispatch_phone:
                    try:
                        # Prefer secrets / env via Streamlit secrets if available
                        import os

                        dispatch_phone = str(os.environ.get("LP_DISPATCH_PHONE") or "").strip()
                        if not dispatch_phone:
                            try:
                                import streamlit as _st

                                dispatch_phone = str(
                                    _st.secrets.get("twilio", {}).get("dispatch_phone", "") or ""
                                ).strip()
                            except Exception:
                                pass
                    except Exception:
                        dispatch_phone = ""
                ok, detail = try_send_sms(
                    dispatch_phone,
                    arrival_msg,
                    "driver_arrival",
                    None,
                )
                if ok:
                    st.success(detail)
                else:
                    st.warning(detail)
            else:
                log_sms_event(None, "driver_arrival", arrival_msg, "driver_app")
                st.success("Arrival logged — send from dispatch Alerts tab.")


def _fetch_lead_options(get_connection: Callable[[], Any]) -> list[dict[str, Any]]:
    """Load shipper/lead rows for the driver bin-estimate dropdown."""
    try:
        with closing(get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT id, company, commodity_focus, bin_capacity_tons, avg_weekly_tons
                FROM leads
                ORDER BY company COLLATE NOCASE
                """
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append({k: row[k] for k in row.keys()})
        return out
    except Exception:
        return []


def _clear_bin_estimate_form_state() -> None:
    """Reset driver bin-estimate form widgets after a successful submit."""
    for key in (
        "bin_est_level",
        "bin_est_lead",
        "bin_est_tons",
        "bin_est_notes",
        "bin_est_photos",
        "bin_est_camera",
        "bin_est_camera_extra",
    ):
        st.session_state.pop(key, None)


def _render_bin_estimate(
    get_connection: Callable[[], Any],
    load: dict[str, Any],
    driver: str,
) -> None:
    """Field form: shipper, bin level, optional tons, silo photos (1–3), notes."""
    from lp_helpers.inventory import (
        BIN_LEVEL_OPTIONS,
        level_to_tons,
        insert_inventory_estimate,
        recalculate_days_of_supply,
        save_inventory_photos,
    )
    from lp_helpers.ui_components import days_of_supply_color, render_days_of_supply

    st.markdown('<div class="cabin-card">', unsafe_allow_html=True)
    st.markdown("### 🗑️ Log Bin Estimate")
    st.caption("Photograph the silo · pick level · submit. Shows on Dispatch Inventory.")

    # Success banner (clears form; stay open so driver sees confirmation)
    if "bin_estimate_saved" in st.session_state:
        saved = st.session_state.pop("bin_estimate_saved")
        st.success(
            f"Saved · **{saved.get('shipper', 'Lead')}** · Level: **{saved['level']}** · "
            f"Est. {saved['tons']:.1f}t"
        )
        if saved.get("days_of_supply") is not None:
            dos = float(saved["days_of_supply"])
            st.markdown(
                f"Days of supply: {render_days_of_supply(dos)}",
                unsafe_allow_html=True,
            )
            # Extra color strip for cabin glanceability
            color_hex = days_of_supply_color(dos)
            st.markdown(
                f"<div style='height:8px;border-radius:4px;background:{color_hex};"
                f"margin:0.35rem 0 0.5rem;'></div>",
                unsafe_allow_html=True,
            )
        else:
            st.info(
                "Days of supply not available — set avg weekly tons on the lead in Dispatch first."
            )
        if st.button(
            "Log another estimate",
            use_container_width=True,
            type="secondary",
            key="bin_est_another",
        ):
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    leads = _fetch_lead_options(get_connection)
    lead_labels: list[str] = []
    lead_by_label: dict[str, dict[str, Any]] = {}
    for lead in leads:
        company = str(lead.get("company") or "Unknown")
        lid = lead.get("id")
        label = f"{company} (#{lid})" if lid is not None else company
        # Disambiguate duplicate company names
        if label in lead_by_label:
            label = f"{company} · id {lid}"
        lead_labels.append(label)
        lead_by_label[label] = lead

    default_index = 0
    shipper_hint = str(load.get("shipper") or "").strip().lower()
    if shipper_hint and lead_labels:
        for i, label in enumerate(lead_labels):
            if shipper_hint in label.lower():
                default_index = i
                break
    elif load.get("lead_id") is not None and lead_labels:
        for i, lead in enumerate(leads):
            if lead.get("id") == load.get("lead_id"):
                default_index = i
                break

    if lead_labels:
        # Prefer session key; seed default shipper from active load once
        default_label = lead_labels[min(default_index, len(lead_labels) - 1)]
        if st.session_state.get("bin_est_lead") not in lead_labels:
            st.session_state.bin_est_lead = default_label
        pick_label = st.selectbox(
            "Shipper / Lead",
            lead_labels,
            key="bin_est_lead",
        )
        selected_lead = lead_by_label.get(pick_label) or {}
        lead_id = selected_lead.get("id")
        try:
            lead_id = int(lead_id) if lead_id is not None else None
        except (TypeError, ValueError):
            lead_id = None
        shipper_name = str(selected_lead.get("company") or pick_label)
        commodity = str(
            selected_lead.get("commodity_focus")
            or load.get("commodity")
            or ""
        )
        capacity = _safe_float(selected_lead.get("bin_capacity_tons"), 24.0) or 24.0
    else:
        st.warning("No leads in database — estimate will save without a shipper link.")
        lead_id = load.get("lead_id")
        try:
            lead_id = int(lead_id) if lead_id is not None else None
        except (TypeError, ValueError):
            lead_id = None
        shipper_name = str(load.get("shipper") or "Unknown")
        commodity = str(load.get("commodity") or "")
        capacity = 24.0

    selected_level = st.radio(
        "Bin Level",
        list(BIN_LEVEL_OPTIONS),
        key="bin_est_level",
        horizontal=False,
    )

    tons_input = st.number_input(
        "Tons estimate (optional)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.5,
        key="bin_est_tons",
        help="Leave at 0 to auto-estimate from bin level × capacity.",
    )

    st.markdown("**Silo photos** (1–3 · camera preferred)")
    camera_shot = None
    if hasattr(st, "camera_input"):
        camera_shot = st.camera_input(
            "Take silo photo",
            key="bin_est_camera",
            help="Opens the phone camera when available.",
        )
    uploads = st.file_uploader(
        "Or upload / gallery (up to 3 total)",
        type=["jpg", "jpeg", "png", "webp", "heic"],
        accept_multiple_files=True,
        key="bin_est_photos",
    )

    photo_files: list[Any] = []
    if camera_shot is not None:
        photo_files.append(camera_shot)
    if uploads:
        for f in uploads:
            if len(photo_files) >= 3:
                break
            photo_files.append(f)
    if photo_files:
        st.caption(f"{len(photo_files)} photo(s) ready")

    notes = st.text_area(
        "Notes (optional)",
        placeholder="Scale ticket, obstruction, unusual fill…",
        key="bin_est_notes",
        height=90,
    )

    if st.button(
        "Submit Bin Estimate",
        use_container_width=True,
        type="primary",
        key="bin_est_submit",
    ):
        if not selected_level:
            st.warning("Pick a bin level first.")
            st.markdown("</div>", unsafe_allow_html=True)
            return
        if not photo_files:
            st.warning("Add at least 1 silo photo (camera or upload).")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        try:
            if tons_input and float(tons_input) > 0:
                est_tons = float(tons_input)
            else:
                est_tons = level_to_tons(str(selected_level), capacity)

            photo_paths = save_inventory_photos(lead_id, load.get("id"), photo_files[:3])

            with closing(get_connection()) as conn:
                insert_inventory_estimate(
                    conn,
                    lead_id=lead_id,
                    load_id=load.get("id"),
                    commodity=commodity,
                    estimated_level=str(selected_level),
                    estimated_tons=est_tons,
                    photo_paths=photo_paths,
                    driver_notes=str(notes or ""),
                    estimated_by=driver,
                )
                days = None
                if lead_id is not None:
                    days = recalculate_days_of_supply(conn, int(lead_id))
                conn.commit()

            try:
                st.cache_data.clear()
            except Exception:
                pass

            st.session_state.bin_estimate_saved = {
                "level": selected_level,
                "tons": est_tons,
                "days_of_supply": days,
                "shipper": shipper_name,
            }
            _clear_bin_estimate_form_state()
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}")

    st.markdown("</div>", unsafe_allow_html=True)

