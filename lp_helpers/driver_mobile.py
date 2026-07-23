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
    --cabin-muted: #94a3b8; --cabin-border: #2a3545; --cabin-orange: #f97316;
    --cabin-danger: #ef4444; --cabin-green: #22c55e;
}
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, sans-serif !important;
    background: var(--cabin-bg) !important; color: var(--cabin-text) !important;
    font-size: 17px !important;
}
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { padding: 0.75rem 1rem 5.5rem !important; max-width: 480px !important; }
.stButton > button {
    min-height: 56px !important; font-weight: 700 !important; font-size: 1.05rem !important;
    border-radius: 14px !important; background: var(--cabin-orange) !important; color: #fff !important;
    border: 2px solid #fb923c !important;
}
/* Secondary outline actions */
.stButton > button[kind="secondary"] {
    background: #1e2937 !important; color: #f1f5f9 !important;
    border: 2px solid var(--cabin-border) !important;
}
.cabin-card {
    background: var(--cabin-card); border: 1px solid var(--cabin-border);
    border-radius: 16px; padding: 1rem; margin-bottom: 0.75rem;
}
.cabin-next {
    background: rgba(249, 115, 22, 0.12); border: 1px solid var(--cabin-orange);
    border-radius: 14px; padding: 0.85rem 1rem; margin-bottom: 0.75rem;
    font-weight: 700; font-size: 1.05rem;
}
.pill { display:inline-block; padding:0.45rem 0.95rem; border-radius:999px;
    font-size:0.9rem; font-weight:700; }
.pill-blue { background:rgba(59,130,246,0.25); color:#93c5fd; }
.pill-green { background:rgba(34,197,94,0.25); color:#4ade80; }
.pill-amber { background:rgba(251,191,36,0.25); color:#fbbf24; }
.stTextInput input, .stTextArea textarea, .stSelectbox > div > div {
    min-height: 48px !important; font-size: 1.05rem !important;
    color: #f1f5f9 !important; background: #1e2937 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
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
    --cabin-muted: #475569; --cabin-border: #cbd5e1; --cabin-orange: #ea580c;
    --cabin-danger: #dc2626; --cabin-green: #16a34a;
}
html, body, [class*="css"] {
    background: var(--cabin-bg) !important; color: var(--cabin-text) !important;
}
.cabin-card { background: var(--cabin-card); border-color: var(--cabin-border); }
.stTextInput input, .stTextArea textarea, .stSelectbox > div > div {
    color: #0f172a !important; background: #f8fafc !important;
    -webkit-text-fill-color: #0f172a !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #0c4a6e !important;
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
        if st.button("Exit", use_container_width=True, key="driver_exit_btn"):
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

    # Primary status actions — full width stack
    st.markdown("#### Status")
    for label, new_status, key in STATUS_ACTIONS:
        is_current = status.lower() == new_status.lower()
        if st.button(
            f"{'✓ ' if is_current else ''}{label}",
            use_container_width=True,
            type="primary" if not is_current else "secondary",
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
        if st.button("Save note", use_container_width=True, key="driver_save_note"):
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

    # GPS — speed + last fix first; coords secondary
    st.markdown("#### GPS")
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
        if st.button("Log Arrival Alert", use_container_width=True, key="driver_arrival_log"):
            log_sms_event(None, "driver_arrival", arrival_msg, "driver_app")
            st.success("Arrival logged — send from dispatch Alerts tab.")
