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
.stButton > button,
.stLinkButton > a,
div[data-testid="stLinkButton"] > a {
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
    """Prefer st.link_button; markdown fallback for older Streamlit."""
    if hasattr(st, "link_button"):
        st.link_button(label, url, use_container_width=True)
        return
    st.markdown(
        f"""
        <a href="{url}" target="_blank" rel="noopener noreferrer" style="
            display:block; text-align:center; text-decoration:none;
            background: linear-gradient(90deg, #ea580c, #f97316);
            color:#fff; border-radius:14px; padding:0.95rem 0.75rem;
            margin-bottom:0.4rem; font-weight:700; font-size:1.05rem;
            min-height:56px; box-shadow:0 4px 14px rgba(249,115,22,0.4);
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
<div style="
    background: rgba(20, 26, 34, 0.98);
    border: 1px solid #2a3545;
    border-left: 5px solid #f97316;
    border-radius: 14px;
    padding: 1rem 1.1rem;
    margin-bottom: 0.75rem;
">
    <div style="font-size: 0.75rem; color: #94a3b8; letter-spacing: 0.5px; margin-bottom: 0.2rem;">ORIGIN</div>
    <div style="font-size: 1.1rem; font-weight: 700; color: #f1f5f9; margin-bottom: 0.75rem;">
        {origin_label}
    </div>
    <div style="font-size: 0.75rem; color: #94a3b8; letter-spacing: 0.5px; margin-bottom: 0.2rem;">DESTINATION</div>
    <div style="font-size: 1.1rem; font-weight: 700; color: #f1f5f9; margin-bottom: 0.55rem;">
        {destination_label}
    </div>
    <div style="font-size: 0.8rem; color: #67e8f9;">
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
        if st.button("Log Arrival Alert", use_container_width=True, key="driver_arrival_log"):
            log_sms_event(None, "driver_arrival", arrival_msg, "driver_app")
            st.success("Arrival logged — send from dispatch Alerts tab.")

    # Bin Estimate — shown after load is delivered
    if str(status).lower() in ("delivered", "complete", "completed"):
        _render_bin_estimate(get_connection, load, owner)

    # Live tracking (secondary) — Traccar status only; navigation is the card above
    st.markdown("""#### Live tracking""")

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
        if st.button("Log Arrival Alert", use_container_width=True, key="driver_arrival_log"):
            log_sms_event(None, "driver_arrival", arrival_msg, "driver_app")
            st.success("Arrival logged — send from dispatch Alerts tab.")


def _render_bin_estimate(
    get_connection: Callable[[], Any],
    load: dict[str, Any],
    driver: str,
) -> None:
    """Simple driver bin-level estimate form."""
    st.markdown('<div class="cabin-card">', unsafe_allow_html=True)
    st.markdown("### 🗑️ Bin Estimate")
    st.caption("How full is the bin? One tap, then submit.")

    if "bin_estimate_saved" in st.session_state:
        saved = st.session_state.pop("bin_estimate_saved")
        st.success(
            f"Saved · Level: **{saved['level']}** · "
            f"Est. {saved['tons']:.1f}t"
        )
        if saved.get("days_of_supply") is not None:
            dos = saved["days_of_supply"]
            color = "green" if dos > 14 else ("orange" if dos >= 7 else "red")
            st.markdown(
                f"Days of supply: **:{color}[{dos:.1f}]** days",
                unsafe_allow_html=True,
            )
        else:
            st.info("Days of supply not available — set avg weekly tons on the lead first.")
        return

    if "bin_est_level" not in st.session_state:
        st.session_state.bin_est_level = None

    levels = ["Empty", "1/4", "1/2", "3/4", "Full"]
    level_cols = st.columns(len(levels))
    for i, lvl in enumerate(levels):
        with level_cols[i]:
            active = st.session_state.bin_est_level == lvl
            if st.button(
                lvl,
                use_container_width=True,
                type="primary" if active else "secondary",
                key=f"bin_lvl_{lvl}",
            ):
                st.session_state.bin_est_level = lvl
                st.rerun()

    selected_level = st.session_state.get("bin_est_level")
    if selected_level:
        st.caption(f"Selected: **{selected_level}**")

    photos = st.file_uploader(
        "Bin photos (optional, up to 3)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="bin_est_photos",
    )
    notes = st.text_input(
        "Driver notes (optional)",
        placeholder="Scale ticket, obstruction, unusual fill…",
        key="bin_est_notes",
    )

    if st.button("SUBMIT BIN ESTIMATE", use_container_width=True, type="primary", key="bin_est_submit"):
        if not selected_level:
            st.warning("Pick a level first.")
            return

        try:
            from lp_helpers.inventory import (
                LEVEL_TONS_MAP,
                ensure_inventory_photos_dir,
                insert_inventory_estimate,
                recalculate_days_of_supply,
                save_inventory_photos,
            )

            lead_id = load.get("lead_id")
            if lead_id is None:
                shipper = str(load.get("shipper", "")).strip()
                try:
                    with closing(get_connection()) as conn:
                        row = conn.execute(
                            "SELECT id FROM leads WHERE company = ? LIMIT 1",
                            (shipper,),
                        ).fetchone()
                        lead_id = int(row["id"]) if row else None
                except Exception:
                    lead_id = None

            photo_files = photos[:3] if photos else []
            photo_paths = save_inventory_photos(lead_id, load.get("id"), photo_files)

            with closing(get_connection()) as conn:
                insert_inventory_estimate(
                    conn,
                    lead_id=lead_id,
                    load_id=load.get("id"),
                    commodity=str(load.get("commodity", "")),
                    estimated_level=selected_level,
                    estimated_tons=float(LEVEL_TONS_MAP.get(selected_level, 0.0) * 24),
                    photo_paths=photo_paths,
                    driver_notes=notes,
                    estimated_by=driver,
                )
                days = None
                if lead_id is not None:
                    days = recalculate_days_of_supply(conn, lead_id)
                conn.commit()

            st.session_state.bin_estimate_saved = {
                "level": selected_level,
                "tons": float(LEVEL_TONS_MAP.get(selected_level, 0.0) * 24),
                "days_of_supply": days,
            }
            st.session_state.bin_est_level = None
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}")

    st.markdown("</div>", unsafe_allow_html=True)

