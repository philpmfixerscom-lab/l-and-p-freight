"""Reusable Streamlit UI render helpers for L & P Dispatch v3.0 Freight OS."""

from __future__ import annotations

import re
from contextlib import closing
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from lp_helpers.database import (
    APP_VERSION,
    DEMO_MODE_KEY,
    NIGHT_MODE_KEY,
    OWNER_ROLE_KEY,
    PRIMARY_LANE,
    TRAILER_PROFILE,
    get_conn,
    get_setting,
    set_setting,
)
from lp_helpers.engines import resolve_voice_path
from lp_helpers.ui_theme import NAV_MORE, NAV_PRIMARY, inject_ui_css

APP_SUBTITLE = "Spruce Pine NC → Central GA · Phillip & Lawson"
AI_DISCLAIMER = (
    "Transparent rule-based suggestions only. Not legal, financial, insurance, "
    "safety, or maintenance advice. Phillip / Lawson makes every final decision."
)
PRIVACY_NOTICE = (
    "PHILLIP / LAWSON OWN ALL DATA: records live locally in ./lp_dispatch.db "
    "and ./attachments/. No cloud sync, telemetry, or third-party sharing is built in."
)
TWILIO_WARNING = (
    "Twilio sends SMS over the internet and incurs per-message cost. "
    "Store credentials only on this machine. Disable by leaving fields blank."
)

_ZONE_CSS = {
    "arrived": "green",
    "approaching": "amber",
    "outside": "red",
    "green": "green",
    "amber": "amber",
    "red": "red",
}


def is_night_mode() -> bool:
    return get_setting(NIGHT_MODE_KEY, "0") == "1"


def render_day_night_toggle(*, key: str = "day_night_toggle") -> None:
    """Day / Night segmented control — persists theme and reruns on change."""
    options = ("☀️ Day", "🌙 Night")
    choice = st.radio(
        "Display mode",
        options,
        index=1 if is_night_mode() else 0,
        horizontal=True,
        key=key,
        label_visibility="collapsed",
    )
    want_night = choice == options[1]
    if want_night != is_night_mode():
        set_setting(NIGHT_MODE_KEY, "1" if want_night else "0")
        st.rerun()


def inject_road_css(night_mode: bool | None = None) -> None:
    """Apply base theme plus map/geofence motion styles."""
    inject_ui_css(night_mode if night_mode is not None else is_night_mode())
    st.markdown(
        """
        <style>
        .lf-map-sim { overflow: hidden; }
        .lf-map-sim .lf-map-truck {
            position: absolute; top: 46%; left: 6%;
            width: 28px; height: 18px;
            background: var(--lf-orange);
            border-radius: 4px;
            animation: lf-truck-drive 8s ease-in-out infinite alternate;
            box-shadow: 0 0 12px rgba(232,93,4,0.55);
        }
        @keyframes lf-truck-drive {
            from { left: 6%; }
            to { left: 82%; }
        }
        .lf-cyber-grid {
            background-image:
                linear-gradient(rgba(232,93,4,0.06) 1px, transparent 1px),
                linear-gradient(90deg, rgba(232,93,4,0.06) 1px, transparent 1px);
            background-size: 24px 24px;
        }
        .lf-geo-radar-ring {
            width: 120px; height: 120px; border-radius: 50%;
            border: 2px solid var(--lf-border);
            position: relative; margin: 0 auto;
        }
        .lf-geo-radar-dot {
            position: absolute; top: 50%; left: 50%;
            width: 10px; height: 10px; border-radius: 50%;
            background: var(--lf-orange);
            transform: translate(-50%, -50%);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _nav_display_label(page_key: str, icon: str = "") -> str:
    for label, key, nav_icon in NAV_PRIMARY + NAV_MORE:
        if key == page_key:
            return f"{icon or nav_icon} {label}"
    return page_key


def is_demo_mode() -> bool:
    return get_setting(DEMO_MODE_KEY, "0") == "1"


def get_owner_role() -> str:
    return get_setting(OWNER_ROLE_KEY, "Phillip")


def privacy_banner(*, compact: bool = False) -> None:
    if compact:
        st.caption(f"🔒 {PRIVACY_NOTICE[:80]}…")
    else:
        st.markdown(f'<div class="lp-privacy">{PRIVACY_NOTICE}</div>', unsafe_allow_html=True)


def ai_banner() -> None:
    st.caption(AI_DISCLAIMER)


def _zone_css(zone: str) -> str:
    return _ZONE_CSS.get(str(zone).lower(), "amber")


def _is_arrived(zone: str) -> bool:
    return str(zone).lower() in ("arrived", "green")


def normalize_geo_result(result: dict[str, Any]) -> dict[str, Any]:
    """Map engines green/amber/red zones to legacy arrived/approaching/outside labels."""
    out = dict(result)
    zone = str(out.get("zone", "")).lower()
    if zone == "green":
        out["zone"] = "arrived"
    elif zone == "amber":
        out["zone"] = "approaching"
    elif zone == "red":
        out["zone"] = "outside"
    return out


def log_geofence_arrival(
    geofence_name: str,
    distance_m: float,
    lat: float,
    lon: float,
    load_id: int | None = None,
) -> None:
    with closing(get_conn()) as conn:
        conn.execute(
            """
            INSERT INTO geofence_events
               (geofence_name, distance_m, latitude, longitude, load_id)
               VALUES (?,?,?,?,?)
            """,
            (geofence_name, distance_m, lat, lon, load_id),
        )
        conn.commit()


def render_app_topbar(page_label: str = "") -> None:
    now = datetime.now().strftime("%a %b %d · %I:%M %p")
    title = page_label or "L & P Freight"
    st.markdown(
        f"""
        <div class="lf-topbar">
            <div>
                <div class="lf-topbar-brand">{title}</div>
                <div class="lf-topbar-sub">{APP_SUBTITLE}</div>
            </div>
            <div class="lf-topbar-right">{now}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str = "") -> None:
    sub_html = (
        f'<div class="lf-page-sub">{subtitle}</div>' if subtitle else ""
    )
    st.markdown(
        f'<div class="lf-page-title">{title}</div>{sub_html}',
        unsafe_allow_html=True,
    )


def render_lane_banner() -> None:
    st.markdown(
        f"""
        <div class="lf-lane-bar">
            <div class="lf-lane-origin">{PRIMARY_LANE['origin']}</div>
            <div class="lf-lane-arrow">→</div>
            <div class="lf-lane-dest">{PRIMARY_LANE['destination']}</div>
            <div class="lf-lane-meta">
                <div>Primary Lane</div>
                <strong>{PRIMARY_LANE['loaded_miles']} mi</strong> · $
                {PRIMARY_LANE['baseline_rate_per_ton']:.0f}/ton
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_row(metrics: dict[str, Any]) -> None:
    loaded_pct = f"{metrics.get('loaded_share', 0):.0%}"
    loaded_color = "green" if metrics.get("loaded_share", 0) >= 0.8 else "amber"
    st.markdown(
        f"""
        <div class="lf-kpi-grid">
            <div class="lf-kpi blue">
                <div class="lf-kpi-label">Loads Hauled</div>
                <div class="lf-kpi-value">{metrics.get('loads', 0)}</div>
            </div>
            <div class="lf-kpi green">
                <div class="lf-kpi-label">Total Revenue</div>
                <div class="lf-kpi-value">${metrics.get('revenue', 0):,.0f}</div>
            </div>
            <div class="lf-kpi {loaded_color}">
                <div class="lf-kpi-label">Loaded Share</div>
                <div class="lf-kpi-value">{loaded_pct}</div>
                <div class="lf-kpi-delta">Target ≥ 80%</div>
            </div>
            <div class="lf-kpi orange">
                <div class="lf-kpi-label">Avg Rate / Ton</div>
                <div class="lf-kpi-value">${metrics.get('avg_rate', 0):.2f}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_roi_hero(metrics: dict[str, Any]) -> None:
    loaded_pct = f"{metrics.get('loaded_share', 0):.0%}"
    deadhead_pct = f"{metrics.get('deadhead_pct', 0):.0%}"
    rev_mi = metrics.get("revenue_per_loaded_mile", 0)
    st.markdown(
        f"""
        <div class="lf-roi-hero">
            <div class="lf-roi-card">
                <div class="lf-roi-label">Revenue / Loaded Mile</div>
                <div class="lf-roi-value">${rev_mi:,.2f}</div>
                <div class="lf-roi-hint">Every loaded mile earns. Target lane:
                {PRIMARY_LANE['loaded_miles']} mi.</div>
            </div>
            <div class="lf-roi-card">
                <div class="lf-roi-label">Loaded Share ROI</div>
                <div class="lf-roi-value">{loaded_pct}</div>
                <div class="lf-roi-hint">≥80% loaded share unlocks rate bonuses (+2–5%).</div>
            </div>
            <div class="lf-roi-card">
                <div class="lf-roi-label">Deadhead Exposure</div>
                <div class="lf-roi-value">{deadhead_pct}</div>
                <div class="lf-roi-hint">{metrics.get('deadhead_miles', 0):,.0f} empty miles —
                minimize via Trimac backhauls.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_load_card(row: pd.Series | dict[str, Any]) -> None:
    if isinstance(row, pd.Series):
        row = row.to_dict()
    origin = row.get("origin") or PRIMARY_LANE["origin"]
    dest = row.get("destination") or "—"
    revenue = float(row.get("total_revenue") or 0)
    weight = float(row.get("weight_tons") or 0)
    voice_badge = (
        '<span class="lf-badge commodity">🎙️ Voice</span>'
        if row.get("voice_audio_path")
        else ""
    )
    st.markdown(
        f"""
        <div class="lf-load-card">
            <div class="lf-load-top">
                <div class="lf-load-bol">{row.get('bol_number', '—')}</div>
                <div class="lf-load-revenue">${revenue:,.0f}</div>
            </div>
            <div class="lf-load-route">
                <strong>{row.get('shipper', '—')}</strong> · {origin} → {dest}
            </div>
            <div class="lf-load-tags">
                <span class="lf-badge commodity">{row.get('commodity', '—')}</span>
                <span class="lf-badge weight">{weight:.1f}t</span>
                <span class="lf-badge status">{row.get('status', 'Logged')}</span>
                <span class="lf-badge date">{row.get('pickup_date', '—')}</span>
                {voice_badge}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_lead_card(lead: pd.Series | dict[str, Any]) -> None:
    if isinstance(lead, pd.Series):
        lead = lead.to_dict()
    phone_clean = re.sub(r"[^\d+]", "", str(lead.get("phone", "")))
    hot = lead.get("status") == "Hot"
    border = "var(--lf-orange)" if hot else "var(--lf-blue)"
    prefix = "🔥 " if hot else ""
    st.markdown(
        f"""
        <div class="lf-lead-card" style="border-left-color:{border}">
            <div class="lf-lead-name">{prefix}{lead.get('company', '—')}</div>
            <div class="lf-lead-phone">
                <a href="tel:{phone_clean}">📞 {lead.get('phone', '—')}</a>
            </div>
            <div class="lf-lead-meta">
                {lead.get('commodity_focus', '—')} · {lead.get('lane_notes', '')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_suggestion_card(row: pd.Series | dict[str, Any]) -> None:
    if isinstance(row, pd.Series):
        row = row.to_dict()
    prio = str(row.get("priority", "Info")).lower()
    css_class = {"critical": "critical", "high": "high", "low": "low"}.get(prio, "")
    st.markdown(
        f"""
        <div class="lf-suggest-card {css_class}">
            <strong>[{row.get('category', '')}] {row.get('title', '')}</strong><br>
            {row.get('detail', '')}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_insight_card(insight: dict[str, str]) -> None:
    prio = insight.get("priority", "Medium")
    traffic = {"Low": "green", "Medium": "amber", "High": "red"}.get(prio, "amber")
    col_a, col_b = st.columns([1, 5])
    with col_a:
        render_traffic_light(traffic, prio)
    with col_b:
        st.markdown(
            f"**{insight.get('category', '')}** — **{insight.get('title', '')}** — "
            f"{insight.get('detail', '')}"
        )


def render_call_log_card(row: pd.Series | dict[str, Any]) -> None:
    if isinstance(row, pd.Series):
        row = row.to_dict()
    company = row.get("company") or "Unknown lead"
    call_type = row.get("call_type") or "—"
    outcome = row.get("outcome") or "—"
    logged = row.get("logged_at") or "—"
    notes = str(row.get("notes") or "").strip()
    voice_path = row.get("voice_audio_path")
    has_voice = bool(voice_path and resolve_voice_path(str(voice_path)))

    st.markdown(
        f"""
        <div class="lf-call-log-card">
            <div class="lf-call-log-top">
                <div class="lf-call-log-company">{company}</div>
                <div class="lf-call-log-meta">{logged}</div>
            </div>
            <div class="lf-call-log-meta">{call_type} · {outcome}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if has_voice:
        st.audio(str(resolve_voice_path(str(voice_path))))
        st.caption(f"🎙️ {voice_path}")
    if notes:
        st.markdown(f"**Notes:** {notes}")
    elif not has_voice:
        st.caption("No voice or text notes recorded.")


def render_traffic_light(status: str, label: str) -> None:
    css = {
        "green": "green",
        "amber": "amber",
        "yellow": "amber",
        "red": "red",
    }.get(str(status).lower(), "amber")
    st.markdown(
        f'<span class="lf-traffic {css}">{label}</span>',
        unsafe_allow_html=True,
    )


def render_live_map_simulation(progress_pct: float = 35.0) -> None:
    truck_left = max(12, min(78, progress_pct))
    st.markdown(
        f"""
        <div class="lf-map-sim lf-cyber-grid">
            <div class="lf-map-route"></div>
            <div class="lf-map-dot origin"></div>
            <div class="lf-map-dot dest"></div>
            <div class="lf-map-dot truck" style="left:{truck_left}%;"></div>
            <div class="lf-map-label" style="left:6%;top:62%;">Spruce Pine NC</div>
            <div class="lf-map-label" style="right:4%;top:62%;">Central GA</div>
            <div style="position:absolute;bottom:0.65rem;left:1rem;font-size:0.75rem;color:#64748b;">
                Live lane simulation · {PRIMARY_LANE['loaded_miles']} mi primary ·
                {progress_pct:.0f}% corridor
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_rings(breakdown: dict[str, dict[str, Any]]) -> None:
    cols = st.columns(4)
    for col, (key, data) in zip(cols, breakdown.items()):
        score = int(data.get("score", 0))
        label = key.replace("_", " ").title()
        col.markdown(
            f"""
            <div class="lf-score-ring" style="border-color:var(--lf-orange);">
                {score}
            </div>
            <div style="text-align:center;font-size:0.75rem;font-weight:700;margin-top:0.35rem;">
                {label}<br><span style="color:var(--lf-muted);">{data.get('weight', '')}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col.caption(data.get("detail", ""))


def render_trailer_fit_badge(
    commodity: str,
    weight_tons: float,
    *,
    max_tons: float = 24,
) -> None:
    if weight_tons > max_tons:
        st.error(
            f"OVERWEIGHT — {weight_tons}t exceeds {max_tons}t lined end-dump limit."
        )
        return
    comm = commodity.lower()
    if any(c in comm for c in ("feldspar", "mica", "spar", "clay", "aggregate", "sand")):
        st.success(f"Trailer fit: ideal for {commodity} on {TRAILER_PROFILE}.")
    elif "fertilizer" in comm or "lime" in comm:
        st.info(f"Trailer fit: {commodity} compatible — verify tarp / liner policy.")
    else:
        st.warning(f"Trailer fit: verify {commodity} with 39ft lined end-dump.")


def render_geofence_alert_banner(result: dict[str, Any]) -> None:
    zone = str(result.get("zone", "")).lower()
    name = result.get("name") or result.get("geofence_name", "—")
    dist = float(result.get("distance_m", 0))
    radius = float(result.get("radius_m", 0))
    miles = float(result.get("miles_away", dist / 1609.34))

    if zone in ("arrived", "green"):
        st.markdown(
            f"""
            <div class="lp-alert-green pulse">✅ ARRIVED — {name}
            <br><span style="font-size:0.9rem;">{dist:.0f}m from center · within
            {radius:.0f}m radius ({miles:.1f} mi)</span></div>
            """,
            unsafe_allow_html=True,
        )
    elif zone in ("approaching", "amber"):
        st.markdown(
            f"""
            <div class="lp-alert-amber">⚠️ APPROACHING — {name}
            <br><span style="font-size:0.9rem;">{dist:.0f}m away · enter zone at ≤
            {radius:.0f}m ({miles:.1f} mi)</span></div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="lp-alert-red">❌ OUTSIDE — {name}
            <br><span style="font-size:0.9rem;">{dist:.0f}m away · need ≤
            {radius:.0f}m to log arrival ({miles:.1f} mi)</span></div>
            """,
            unsafe_allow_html=True,
        )


def render_geofence_proximity_card(result: dict[str, Any]) -> None:
    zone = _zone_css(str(result.get("zone", "amber")))
    pct = float(result.get("proximity_pct", 0))
    st.markdown(
        f"""
        <div class="lf-geo-card {zone}">
            <strong>{result.get('name', result.get('geofence_name', '—'))}</strong>
            <span class="lf-badge status">{result.get('geofence_type', 'Zone')}</span>
            <div style="font-size:0.85rem;color:var(--lf-muted);margin-top:0.25rem;">
                {result.get('location_label', '')} · Haversine: {result.get('distance_m', 0):.0f}m
                ({result.get('miles_away', 0):.1f} mi) · radius {result.get('radius_m', 0):.0f}m
            </div>
            <div class="lf-geo-progress">
                <div class="lf-geo-progress-fill {zone}" style="width:{pct}%;"></div>
            </div>
            <div style="font-size:0.78rem;color:var(--lf-muted);">
                Proximity {pct:.0f}% · Zone: <strong>{zone.upper()}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_geofence_radar_summary(results: list[dict[str, Any]]) -> None:
    if not results:
        return
    best = results[0]
    zone = str(best.get("zone", "")).upper()
    st.markdown(
        f"""
        <div class="lf-geo-radar">
            <div>
                <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.08em;color:var(--lf-muted);">Nearest Zone</div>
                <div style="font-size:1.15rem;font-weight:800;color:var(--lf-text);">
                    {best.get('name', best.get('geofence_name', '—'))}
                </div>
                <div style="font-size:0.85rem;color:var(--lf-muted);">
                    {best.get('distance_m', 0):.0f}m · {zone}
                </div>
            </div>
            <div class="lf-geo-radar-ring">
                <div class="lf-geo-radar-dot {_zone_css(best.get('zone', ''))}"></div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.08em;color:var(--lf-muted);">Haversine</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:1rem;font-weight:700;
                    color:var(--lf-orange);">WGS84 · meters</div>
                <div style="font-size:0.82rem;color:var(--lf-muted);">
                    {len(results)} active geofences
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_geofence_event_card(row: pd.Series | dict[str, Any]) -> None:
    if isinstance(row, pd.Series):
        row = row.to_dict()
    load_ref = f" · Load #{int(row['load_id'])}" if row.get("load_id") else ""
    st.markdown(
        f"""
        <div class="lf-call-log-card">
            <div class="lf-call-log-top">
                <div class="lf-call-log-company">📍 {row.get('geofence_name', '—')}</div>
                <div class="lf-call-log-meta">{row.get('logged_at', '—')}</div>
            </div>
            <div class="lf-call-log-meta">
                {row.get('distance_m', 0):.0f}m from center ·
                ({row.get('latitude', 0):.4f}, {row.get('longitude', 0):.4f}){load_ref}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )