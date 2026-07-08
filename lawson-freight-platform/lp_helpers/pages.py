"""All page render functions for L & P Dispatch v3.0 Freight OS Streamlit app."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED

import pandas as pd
import streamlit as st

from lp_helpers.analytics_dashboard import render_analytics_page
from lp_helpers.bol_export import bol_pdf_filename
from lp_helpers.database import (
    APP_VERSION,
    ATTACHMENTS_DIR,
    COMMODITY_OPTIONS,
    DB_PATH,
    DEMO_MODE_KEY,
    GEO_POSITION_PRESETS,
    MIGRATION_REPORT_KEY,
    NIGHT_MODE_KEY,
    OWNER_ROLE_KEY,
    PRIMARY_LANE,
    TRAILER_MAX_TONS,
    TRAILER_PROFILE,
    calculate_rate,
    clear_cache,
    fetch_ai_suggestions,
    fetch_call_logs,
    fetch_compliance,
    fetch_fuel,
    fetch_geofence_events,
    fetch_geofences,
    fetch_leads,
    fetch_loads,
    fetch_maintenance,
    fetch_sms_log,
    fetch_telematics,
    generate_bol_number,
    get_conn,
    get_setting,
    migrate_legacy_databases,
    nuclear_delete_all_data,
    seed_demo_data,
    set_setting,
)
from lp_helpers.engines import (
    BULK_IMPORT_REQUIRED,
    build_bulk_template_xlsx,
    bulk_import_template_df,
    bulk_insert_loads,
    check_geofence_proximity,
    clear_voice_session,
    dashboard_metrics,
    generate_bol_pdf,
    generate_invoice_preview_pdf,
    generate_performance_report_pdf,
    generate_predictive_insights,
    generate_sms_text,
    ifta_summary,
    log_sms,
    merge_voice_notes,
    normalize_import_dataframe,
    parse_uploaded_load_file,
    persist_ai_suggestions,
    render_voice_input_panel,
    run_ai_suggestion_engine,
    save_voice_recording,
    score_load_intelligence,
    send_twilio_sms,
    simulate_document_ocr,
    simulate_rate_profit,
    smart_arrival_prefill,
    summarize_voice_with_ai,
    validate_bulk_dataframe,
)
from lp_helpers.followup_templates import render_followup_panel
from lp_helpers.load_board import render_load_board_page
from lp_helpers.ui_components import (
    PRIVACY_NOTICE,
    TWILIO_WARNING,
    ai_banner,
    get_owner_role,
    is_demo_mode,
    log_geofence_arrival,
    normalize_geo_result,
    render_call_log_card,
    render_geofence_alert_banner,
    render_geofence_event_card,
    render_geofence_proximity_card,
    render_geofence_radar_summary,
    render_insight_card,
    render_kpi_row,
    render_lane_banner,
    render_lead_card,
    render_live_map_simulation,
    render_load_card,
    render_page_header,
    render_roi_hero,
    render_score_rings,
    render_suggestion_card,
    render_traffic_light,
    render_trailer_fit_badge,
)

BULK_IMPORT_OPTIONAL = ["loaded_miles", "notes"]
ASSET_OPTIONS = [
    "Tractor",
    "39ft End-Dump Trailer",
    "Tarp System",
    "Hydraulics",
    "Other",
]
FOUNDATION_TABLES = (
    "leads",
    "loads",
    "call_logs",
    "compliance",
    "telematics",
    "fuel",
    "maintenance",
    "geofences",
    "geofence_events",
    "sms_log",
    "app_settings",
    "opportunities",
)
CALL_TYPES = ["Outbound", "Inbound", "Follow-up", "Rate Quote"]
CALL_OUTCOMES = [
    "No answer",
    "Left voicemail",
    "Spoke — load offered",
    "Spoke — no load",
    "Callback scheduled",
]
COMPLIANCE_STATUSES = ["Active", "Verify", "Pending", "Due Soon", "Required"]
GEOFENCE_APPROACH_MULTIPLIER = 2.0


def nav_to(page: str) -> None:
    st.session_state.nav_tab = page
    st.rerun()


def apply_load_prefill(prefill: dict[str, Any]) -> None:
    """Push cross-page values into Load Logger widget session state."""
    if "shipper" in prefill:
        st.session_state.ll_shipper = prefill["shipper"]
    if prefill.get("commodity") in COMMODITY_OPTIONS:
        st.session_state.ll_commodity = prefill["commodity"]
    if "weight_tons" in prefill:
        st.session_state.ll_weight = float(prefill["weight_tons"])
    if "miles" in prefill:
        st.session_state.ll_miles = float(prefill["miles"])
    if "loaded_miles" in prefill:
        st.session_state.ll_loaded_miles = float(prefill["loaded_miles"])
    if "destination" in prefill:
        st.session_state.ll_destination = prefill["destination"]
    if "pickup_date" in prefill:
        st.session_state.ll_pickup = prefill["pickup_date"]
    if "notes" in prefill:
        st.session_state.ll_notes = prefill["notes"]
    if "rate_per_ton" in prefill:
        st.session_state.ll_rate_override = float(prefill["rate_per_ton"])


def _enrich_geo_results(
    lat: float, lon: float, geofences_df: pd.DataFrame
) -> list[dict[str, Any]]:
    raw = check_geofence_proximity(lat, lon, geofences_df)
    enriched: list[dict[str, Any]] = []
    if geofences_df is None or geofences_df.empty:
        return [normalize_geo_result(r) for r in raw]

    geo_by_name = {str(g["name"]): g for _, g in geofences_df.iterrows()}
    for item in raw:
        merged = dict(item)
        name = str(item.get("geofence_name") or item.get("name", ""))
        if name in geo_by_name:
            g = geo_by_name[name]
            merged.update(
                {
                    "name": name,
                    "geofence_type": g.get("geofence_type", "Zone"),
                    "location_label": g.get("location_label", ""),
                    "radius_m": float(g.get("radius_m", item.get("radius_m", 0))),
                }
            )
        enriched.append(normalize_geo_result(merged))
    return enriched


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def render_dashboard() -> None:
    render_page_header(
        "Home",
        f"Hi {get_owner_role()} — your lane at a glance",
    )
    render_lane_banner()

    loads_df = fetch_loads()
    metrics = dashboard_metrics(loads_df)

    if is_demo_mode():
        st.info(
            "Demo mode is on — sample data loaded. Turn off in Settings → More tools."
        )

    render_kpi_row(metrics)
    render_roi_hero(metrics)

    st.markdown('<div class="lf-section-header">Quick actions</div>', unsafe_allow_html=True)
    q1, q2, q3 = st.columns(3)
    if q1.button("Log a load", use_container_width=True, type="primary"):
        nav_to("Load Logger")
    if q2.button("Load board", use_container_width=True):
        nav_to("Load Board")
    if q3.button("Call a lead", use_container_width=True):
        nav_to("Leads & Calls")

    st.markdown('<div class="lf-section-header">Recent loads</div>', unsafe_allow_html=True)
    if loads_df.empty:
        st.info("No loads yet. Tap **Log a load** above to get started.")
    else:
        for _, row in loads_df.head(6).iterrows():
            render_load_card(row)

    with st.expander("Hot leads & tips", expanded=False):
        leads_df = fetch_leads()
        for _, lead in leads_df.iterrows():
            if lead.get("status") == "Hot":
                render_lead_card(lead)

        suggestions = run_ai_suggestion_engine(loads_df, leads_df)
        persist_ai_suggestions(suggestions)
        for _, row in fetch_ai_suggestions().head(3).iterrows():
            render_suggestion_card(row)

    with st.expander("Lane map", expanded=False):
        progress = metrics.get("loaded_share", 0) * 100 if metrics.get("loaded_share") else 35.0
        render_live_map_simulation(progress)


# ---------------------------------------------------------------------------
# Load Logger
# ---------------------------------------------------------------------------


def render_load_logger() -> None:
    render_page_header("Log a Load", "Enter one load, or bulk-import from CSV below")
    render_lane_banner()

    prefill = st.session_state.pop("load_prefill", {})
    if prefill:
        apply_load_prefill(prefill)
        st.success("Prefill loaded — review fields and save when ready.")

    voice_path, voice_notes = render_voice_input_panel(
        "load_logger",
        category="load",
        panel_title="🎙️ Dispatch Voice Note",
        panel_hint=(
            "Record load details hands-free — saved locally. "
            "Use text fallback if cab is loud."
        ),
        text_label="Text fallback (shipper, weight, destination…)",
        text_placeholder=(
            "e.g. Sibelco feldspar 24t to Kohler — or type anything you couldn't record."
        ),
    )

    if voice_notes or voice_path:
        ai_sum = summarize_voice_with_ai(voice_notes or "voice memo recorded", "dispatch")
        with st.expander("🧠 AI Voice Summary", expanded=True):
            st.write(ai_sum.get("summary", ""))
            if ai_sum.get("fields"):
                st.json(ai_sum["fields"])
            for act in ai_sum.get("actions", []):
                st.markdown(f"- {act}")

    with st.form("single_load_form"):
        c1, c2 = st.columns(2)
        shipper = c1.text_input("Shipper *", key="ll_shipper")
        commodity = c2.selectbox("Commodity *", COMMODITY_OPTIONS, key="ll_commodity")
        c3, c4, c5 = st.columns(3)
        weight = c3.number_input(
            "Weight (tons) *",
            min_value=0.0,
            max_value=30.0,
            value=24.0,
            step=0.5,
            key="ll_weight",
        )
        miles = c4.number_input(
            "Total Miles *",
            min_value=0.0,
            value=float(PRIMARY_LANE["loaded_miles"]),
            step=1.0,
            key="ll_miles",
        )
        loaded_miles = c5.number_input(
            "Loaded Miles",
            min_value=0.0,
            value=float(PRIMARY_LANE["loaded_miles"]),
            step=1.0,
            key="ll_loaded_miles",
        )
        c6, c7 = st.columns(2)
        pickup = c6.date_input("Pickup Date", value=date.today(), key="ll_pickup")
        destination = c7.text_input(
            "Destination",
            value=PRIMARY_LANE["destination"],
            key="ll_destination",
        )
        notes = st.text_area("Structured notes (optional)", key="ll_notes")
        submitted = st.form_submit_button("LOG LOAD", use_container_width=True)

    if weight > 0 and commodity:
        render_trailer_fit_badge(commodity, weight, max_tons=TRAILER_MAX_TONS)

    if submitted:
        if not shipper.strip():
            st.error("Shipper is required.")
        elif weight > TRAILER_MAX_TONS:
            st.error(f"Weight exceeds {TRAILER_MAX_TONS}-ton trailer limit.")
        elif weight <= 0 or miles <= 0:
            st.error("Weight and miles must be greater than zero.")
        else:
            rate, revenue = calculate_rate(weight, miles, loaded_miles, commodity)
            bol = generate_bol_number()
            deadhead = max(0.0, miles - loaded_miles)
            combined_notes = merge_voice_notes(notes, voice_path)
            with closing(get_conn()) as conn:
                conn.execute(
                    """
                    INSERT INTO loads (
                        bol_number, shipper, commodity, weight_tons, miles,
                        loaded_miles, deadhead_miles, pickup_date, origin, destination,
                        rate_per_ton, total_revenue, notes, voice_audio_path, status
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        bol,
                        shipper.strip(),
                        commodity,
                        weight,
                        miles,
                        loaded_miles,
                        deadhead,
                        str(pickup),
                        PRIMARY_LANE["origin"],
                        destination.strip(),
                        rate,
                        revenue,
                        combined_notes,
                        voice_path,
                        "Logged",
                    ),
                )
                conn.commit()
            clear_cache()
            clear_voice_session("load_logger")
            st.session_state.last_logged_load = {
                "bol_number": bol,
                "shipper": shipper.strip(),
                "commodity": commodity,
                "weight_tons": weight,
                "destination": destination.strip(),
                "rate_per_ton": rate,
                "total_revenue": revenue,
                "origin": PRIMARY_LANE["origin"],
                "pickup_date": str(pickup),
            }
            st.success(f"Load logged — BOL {bol} · ${revenue:,.2f}")
            st.rerun()

    last_load = st.session_state.get("last_logged_load")
    if last_load and not st.session_state.get("dismiss_load_followup"):
        render_followup_panel(
            "Send Follow-up (after load logged)",
            last_load,
            template_keys=["load_logged_thanks", "rate_confirmation", "pickup_reminder"],
            panel_key="load_followup",
        )
        if st.button("Dismiss load follow-up", key="dismiss_load_followup"):
            st.session_state.pop("last_logged_load", None)
            st.rerun()

    with st.expander("📥 Bulk Load Import", expanded=False):
        st.markdown('<div class="lf-section-header">📥 Bulk Load Import</div>', unsafe_allow_html=True)
        st.caption(
            f"Required: {', '.join(BULK_IMPORT_REQUIRED)} · Optional: "
            f"{', '.join(BULK_IMPORT_OPTIONAL)} · Max weight: {TRAILER_MAX_TONS}t · "
            f"validate before import."
        )
        template_df = bulk_import_template_df()
        dl1, dl2 = st.columns(2)
        dl1.download_button(
            "Download Template CSV",
            template_df.to_csv(index=False).encode(),
            "lp_dispatch_bulk_import_template.csv",
            "text/csv",
            use_container_width=True,
        )
        dl2.download_button(
            "Download Template XLSX",
            build_bulk_template_xlsx(),
            "lp_dispatch_bulk_import_template.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"], key="bulk_upload")
        if uploaded is not None:
            try:
                raw_df = parse_uploaded_load_file(uploaded)
                import_df = normalize_import_dataframe(raw_df)
                if import_df.empty:
                    st.warning("File has no data rows after cleanup.")
                else:
                    required_missing = [
                        c for c in BULK_IMPORT_REQUIRED if c not in import_df.columns
                    ]
                    if required_missing:
                        st.error(
                            f"Missing required columns: {', '.join(required_missing)}. "
                            f"Found columns: {', '.join(import_df.columns)}"
                        )
                    else:
                        st.dataframe(import_df.head(20), use_container_width=True, hide_index=True)
                        if st.button("VALIDATE IMPORT", use_container_width=True, type="primary"):
                            validation = validate_bulk_dataframe(import_df)
                            st.session_state.bulk_validation = validation
                            st.session_state.bulk_filename = uploaded.name
                        validation = st.session_state.get("bulk_validation")
                        if validation:
                            st.markdown(
                                f"""
                                <span class="lf-bulk-stat ok">{validation['ok_count']} OK</span>
                                <span class="lf-bulk-stat warn">{validation['warn_count']} WARN</span>
                                <span class="lf-bulk-stat fail">{validation['fail_count']} FAIL</span>
                                <span style="font-size:0.85rem;color:var(--lf-muted);">
                                of {validation['total_rows']} rows</span>
                                """,
                                unsafe_allow_html=True,
                            )
                            if validation["valid_rows"]:
                                st.info(
                                    f"{len(validation['valid_rows'])} rows pass validation · "
                                    f"est. revenue ${validation['total_revenue']:,.0f}"
                                )
                            if validation["fail_count"]:
                                st.warning(
                                    f"{validation['fail_count']} rows failed — fix file and re-validate."
                                )
                            with st.expander("Validation preview", expanded=True):
                                st.dataframe(
                                    validation["preview_df"],
                                    use_container_width=True,
                                    hide_index=True,
                                )
                            if validation["valid_rows"] and st.button(
                                f"IMPORT {len(validation['valid_rows'])} VALID ROWS",
                                use_container_width=True,
                            ):
                                count = bulk_insert_loads(validation["valid_rows"])
                                st.session_state.pop("bulk_validation", None)
                                st.success(
                                    f"Imported {count} loads · "
                                    f"${validation['total_revenue']:,.0f} total revenue."
                                )
                                st.rerun()
            except Exception as exc:
                st.error(f"Import failed: {exc}")

    st.markdown('<div class="lf-section-header">📋 All Loads</div>', unsafe_allow_html=True)
    loads_df = fetch_loads()
    if loads_df.empty:
        st.caption("No loads logged yet.")
    else:
        for _, row in loads_df.head(20).iterrows():
            render_load_card(row)


# ---------------------------------------------------------------------------
# Leads & Calls
# ---------------------------------------------------------------------------


def render_leads_calls() -> None:
    render_page_header("Leads", "Shipper contacts, follow-ups, and call notes")
    leads = fetch_leads()
    if leads.empty:
        st.warning("No leads found.")
        return

    st.markdown('<div class="lf-section-header">🔥 Shipper Leads</div>', unsafe_allow_html=True)
    lc1, lc2 = st.columns(2)
    for i, (_, lead) in enumerate(leads.iterrows()):
        with (lc1 if i % 2 == 0 else lc2):
            render_lead_card(lead)

    st.markdown('<div class="lf-section-header">📨 Send Follow-up</div>', unsafe_allow_html=True)
    follow_lead_map = {
        f"{row['company']} — {row.get('contact_name', 'Dispatch')}": row
        for _, row in leads.iterrows()
    }
    follow_label = st.selectbox("Lead for follow-up", list(follow_lead_map.keys()), key="crm_follow_lead")
    follow_lead = follow_lead_map[follow_label].to_dict()
    render_followup_panel(
        "Send Follow-up",
        {
            "contact_name": follow_lead.get("contact_name", "there"),
            "company": follow_lead.get("company", "Shipper"),
            "commodity": follow_lead.get("commodity_focus", "Feldspar").split(",")[0].strip(),
            "phone": follow_lead.get("phone", ""),
        },
        template_keys=[
            "feldspar_discussion",
            "rate_confirmation",
            "pickup_reminder",
            "callback_request",
            "bulkloads_opportunity",
        ],
        panel_key="crm_followup",
    )

    st.markdown('<div class="lf-section-header">📝 Log Call</div>', unsafe_allow_html=True)
    lead_options = {row["company"]: int(row["id"]) for _, row in leads.iterrows()}
    selected_company = st.selectbox("Lead", list(lead_options.keys()), key="call_lead_sel")
    lead_id = lead_options[selected_company]
    c1, c2 = st.columns(2)
    call_type = c1.selectbox("Call Type", CALL_TYPES, key="call_type_sel")
    outcome = c2.selectbox("Outcome", CALL_OUTCOMES, key="call_outcome_sel")

    voice_path, text_notes = render_voice_input_panel(
        f"call_{lead_id}",
        category="call",
        ref_id=lead_id,
        panel_title="🎙️ Call Voice Memo",
        panel_hint="Record the conversation or rate quote — saved locally to ./attachments/.",
        text_label="Text fallback",
        text_placeholder=(
            "Shipper name, rate quoted, callback time — use if you can't record."
        ),
    )

    if text_notes or voice_path:
        ai_sum = summarize_voice_with_ai(text_notes or "call logged", "call")
        with st.expander("🧠 AI Voice + Text Summary", expanded=False):
            st.write(ai_sum.get("summary", ""))
            if ai_sum.get("fields"):
                st.json(ai_sum["fields"])
            for act in ai_sum.get("actions", []):
                st.markdown(f"- {act}")

    if st.button("SAVE CALL LOG", use_container_width=True, type="primary"):
        combined = merge_voice_notes(text_notes, voice_path)
        with closing(get_conn()) as conn:
            conn.execute(
                """
                INSERT INTO call_logs (
                    lead_id, call_type, notes, outcome, voice_audio_path
                ) VALUES (?,?,?,?,?)
                """,
                (lead_id, call_type, combined, outcome, voice_path),
            )
            conn.execute(
                "UPDATE leads SET last_contact = datetime('now') WHERE id = ?",
                (lead_id,),
            )
            conn.commit()
        clear_cache()
        clear_voice_session(f"call_{lead_id}")
        st.success(f"Call logged for {selected_company}.")
        st.rerun()

    st.markdown('<div class="lf-section-header">Recent calls</div>', unsafe_allow_html=True)
    logs_df = fetch_call_logs()
    if logs_df.empty:
        st.caption("No calls logged yet.")
    else:
        for _, row in logs_df.head(10).iterrows():
            render_call_log_card(row)


# ---------------------------------------------------------------------------
# AI Intelligence
# ---------------------------------------------------------------------------


def render_ai_intelligence() -> None:
    render_page_header("Rates", "Score loads and estimate profit before you haul")
    loads_df = fetch_loads()
    leads_df = fetch_leads()

    tab1, tab2 = st.tabs(["Load Scorer", "Rate / Profit Simulator"])

    with tab1:
        c1, c2 = st.columns(2)
        shipper_options = ["Other"] + (
            leads_df["company"].tolist() if not leads_df.empty else []
        )
        shipper_pick = c1.selectbox("Shipper", shipper_options, key="ai_shipper_pick")
        if shipper_pick == "Other":
            shipper = c1.text_input("Shipper name", key="ai_shipper_text")
        else:
            shipper = shipper_pick
        commodity = c2.selectbox("Commodity", COMMODITY_OPTIONS, key="ai_commodity")
        c3, c4, c5 = st.columns(3)
        weight = c3.number_input("Weight (tons)", min_value=0.0, value=24.0, key="ai_weight")
        miles = c4.number_input(
            "Miles",
            min_value=0.0,
            value=float(PRIMARY_LANE["loaded_miles"]),
            key="ai_miles",
        )
        loaded = c5.number_input(
            "Loaded miles",
            min_value=0.0,
            value=float(PRIMARY_LANE["loaded_miles"]),
            key="ai_loaded",
        )

        if st.button("SCORE THIS LOAD", use_container_width=True, type="primary"):
            result = score_load_intelligence(
                shipper, commodity, weight, miles, loaded, loads_df
            )
            st.session_state.last_score = result

        result = st.session_state.get("last_score")
        if result:
            st.markdown(
                f"""
                <div class="lf-score-ring">{result['score']}</div>
                <div style="text-align:center;font-weight:800;margin-top:0.5rem;">
                Grade {result['grade']} · {result['recommendation']}</div>
                """,
                unsafe_allow_html=True,
            )
            st.success(result.get("roi_message", ""))
            render_score_rings(result.get("breakdown", {}))
            for key, b in result.get("breakdown", {}).items():
                traffic = (
                    "green"
                    if b["score"] >= 75
                    else "amber"
                    if b["score"] >= 55
                    else "red"
                )
                col_s, col_d = st.columns([1, 4])
                with col_s:
                    render_traffic_light(traffic, f"{b['score']}/100")
                with col_d:
                    st.markdown(
                        f"**{key.replace('_', ' ').title()}** ({b.get('weight', '')}) — "
                        f"{b.get('detail', '')}"
                    )

    with tab2:
        s1, s2, s3 = st.columns(3)
        sw = s1.number_input("Sim weight (t)", min_value=0.0, value=24.0, key="sim_w")
        sm = s2.number_input(
            "Sim miles",
            min_value=0.0,
            value=float(PRIMARY_LANE["loaded_miles"]),
            key="sim_m",
        )
        sl = s3.number_input(
            "Sim loaded mi",
            min_value=0.0,
            value=float(PRIMARY_LANE["loaded_miles"]),
            key="sim_lm",
        )
        sc = st.selectbox("Sim commodity", COMMODITY_OPTIONS, key="sim_c")
        override = st.number_input(
            "Rate override $/ton (0 = auto)",
            min_value=0.0,
            value=0.0,
            key="sim_rate_override",
        )
        rate_override = override if override > 0 else None
        sim = simulate_rate_profit(sw, sm, sl, sc, rate_override)
        st.markdown(
            f"""
            <div class="lf-glass" style="padding:1rem;margin:0.5rem 0;">
            Transparent L & P rate model — owner makes final call.
            </div>
            """,
            unsafe_allow_html=True,
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Revenue", f"${sim['revenue']:,.0f}")
        m2.metric("Fuel est.", f"${sim['fuel_est']:,.0f}")
        m3.metric("Margin est.", f"${sim['margin_est']:,.0f}")
        m4.metric("Margin %", f"{sim['margin_pct']:.0%}")
        st.caption(f"${sim['per_mile']:.2f}/loaded mi · L & P Dispatch transparent model")


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


def render_insights() -> None:
    render_page_header(
        "Predictive Insights",
        "Trends · maintenance · lane performance · backhauls",
    )
    loads_df = fetch_loads()
    maint_df = fetch_maintenance()
    insights = generate_predictive_insights(loads_df, maint_df)

    for ins in insights:
        render_insight_card(ins)

    if not loads_df.empty:
        st.markdown(
            '<div class="lf-section-header">📈 Revenue Trend (local data)</div>',
            unsafe_allow_html=True,
        )
        chart_df = loads_df.copy()
        chart_df["pickup_date"] = pd.to_datetime(chart_df["pickup_date"], errors="coerce")
        trend = (
            chart_df.dropna(subset=["pickup_date"])
            .groupby(chart_df["pickup_date"].dt.date)["total_revenue"]
            .sum()
            .reset_index()
        )
        trend.columns = ["date", "revenue"]
        if not trend.empty:
            st.line_chart(trend.set_index("date"))

    st.markdown(
        '<div class="lf-section-header">🔁 Suggested Backhauls</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="lf-panel lf-glass">
        <strong>Trimac Central GA → Spruce Pine</strong><br>
        Est. saves <strong>~40 deadhead mi</strong> · Call 828-765-7491 when lane is quiet.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def render_documents() -> None:
    render_page_header(
        "Document AI",
        "BOL / scale ticket capture · simulated OCR · auto-create load",
    )
    st.caption(
        "Offline placeholder OCR — swap for Tesseract or cloud API when ready. "
        "Owner reviews all fields."
    )

    tab1, tab2 = st.tabs(["Photo Capture", "Upload Scan"])

    with tab1:
        photo = st.camera_input("Capture BOL or scale ticket", key="doc_cam")
        hint = st.text_input(
            "Optional hint text (shipper, tons…)",
            key="ocr_hint_cam",
        )
        if st.button("EXTRACT FROM PHOTO", use_container_width=True, type="primary"):
            if photo:
                path = save_voice_recording(photo.getvalue(), category="doc_scan")
                st.session_state.ocr_result = simulate_document_ocr(
                    "doc_scan", hint_text=hint
                )
                st.session_state.doc_scan_path = path
                st.success("Captured — stored locally")
            else:
                st.warning("Take a photo first.")

    with tab2:
        upload = st.file_uploader(
            "Upload image/PDF scan",
            type=["png", "jpg", "jpeg", "webp"],
            key="doc_upload",
        )
        hint2 = st.text_input("Optional hint text", key="ocr_hint_up")
        if st.button("EXTRACT FROM UPLOAD", use_container_width=True, type="primary"):
            if upload:
                fname = f"scan_{uuid_hex()}{Path(upload.name).suffix}"
                ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
                (ATTACHMENTS_DIR / fname).write_bytes(upload.getvalue())
                st.session_state.ocr_result = simulate_document_ocr(
                    upload.name, hint_text=hint2
                )
                st.session_state.doc_scan_path = str(ATTACHMENTS_DIR / fname)
                st.success("Uploaded — stored locally")
            else:
                st.warning("Upload a file first.")

    extracted = st.session_state.get("ocr_result")
    if extracted:
        st.markdown(
            '<div class="lf-section-header">🔍 OCR Extraction Result</div>',
            unsafe_allow_html=True,
        )
        st.info(
            f"Simulated {extracted.get('doc_type', 'document')} · confidence "
            f"{extracted.get('confidence', 0):.0%}"
        )
        e1, e2, e3 = st.columns(3)
        shipper = e1.text_input("Shipper", value=extracted.get("shipper", ""))
        commodity = e2.selectbox(
            "Commodity",
            COMMODITY_OPTIONS,
            index=COMMODITY_OPTIONS.index(extracted.get("commodity", "Feldspar"))
            if extracted.get("commodity") in COMMODITY_OPTIONS
            else 0,
        )
        weight = e3.number_input(
            "Weight (t)",
            min_value=0.0,
            value=float(extracted.get("weight_tons", 24)),
        )
        e4, e5 = st.columns(2)
        miles = e4.number_input(
            "Miles",
            min_value=0.0,
            value=float(extracted.get("miles", PRIMARY_LANE["loaded_miles"])),
        )
        destination = e5.text_input(
            "Destination",
            value=extracted.get("destination", PRIMARY_LANE["destination"]),
        )
        score = score_load_intelligence(
            shipper,
            commodity,
            weight,
            miles,
            extracted.get("loaded_miles", miles),
            fetch_loads(),
        )
        st.info(score.get("roi_message", ""))

        if st.button("CREATE LOAD FROM OCR", use_container_width=True, type="primary"):
            rate, revenue = calculate_rate(
                weight,
                miles,
                extracted.get("loaded_miles", miles),
                commodity,
            )
            bol = generate_bol_number()
            deadhead = max(0.0, miles - float(extracted.get("loaded_miles", miles)))
            with closing(get_conn()) as conn:
                conn.execute(
                    """
                    INSERT INTO loads (
                        bol_number, shipper, commodity, weight_tons, miles,
                        loaded_miles, deadhead_miles, pickup_date, origin, destination,
                        rate_per_ton, total_revenue, notes, status
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        bol,
                        shipper,
                        commodity,
                        weight,
                        miles,
                        extracted.get("loaded_miles", miles),
                        deadhead,
                        str(date.today()),
                        PRIMARY_LANE["origin"],
                        destination,
                        rate,
                        revenue,
                        f"OCR import · confidence {extracted.get('confidence', 0):.0%}",
                        "Logged",
                    ),
                )
                conn.commit()
            clear_cache()
            st.session_state.pop("ocr_result", None)
            st.success(f"Load created — BOL {bol} · ${revenue:,.0f}")
            st.session_state.load_prefill = {
                "shipper": shipper,
                "commodity": commodity,
                "weight_tons": weight,
                "miles": miles,
            }
            nav_to("Load Logger")


def uuid_hex() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def render_reports() -> None:
    render_page_header(
        "BOL & Reports",
        "Download PDF bills of lading and performance reports",
    )
    loads_df = fetch_loads()
    tab1, tab2, tab3 = st.tabs(["BOL PDF", "Performance Report", "Invoice Preview"])

    with tab1:
        if loads_df.empty:
            st.info("Log a load first in Load Logger.")
        else:
            options = {
                f"{r['bol_number']} — {r['shipper']}": r.to_dict()
                for _, r in loads_df.iterrows()
            }
            load = options[st.selectbox("Load", list(options.keys()), key="bol_gen_sel")]
            if st.button("Download PDF BOL", use_container_width=True, type="primary"):
                try:
                    pdf = generate_bol_pdf(load)
                    pdf_name = bol_pdf_filename(load)
                    st.session_state.bol_pdf_bytes = pdf
                    st.session_state.bol_pdf_name = pdf_name
                    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
                    (ATTACHMENTS_DIR / pdf_name).write_bytes(pdf)
                    st.success(f"L & P Freight BOL ready — {pdf_name}")
                except Exception as exc:
                    st.error(f"BOL generation failed: {exc}")
            if st.session_state.get("bol_pdf_bytes"):
                st.download_button(
                    "⬇️ Save / Print PDF BOL",
                    st.session_state.bol_pdf_bytes,
                    st.session_state.get("bol_pdf_name", "bol.pdf"),
                    "application/pdf",
                    key="bol_dl_btn",
                    use_container_width=True,
                )
                st.caption("Print from your PDF viewer or AirDrop to phone for cab use.")

    with tab2:
        if loads_df.empty:
            st.info("Log a load first.")
        else:
            if st.button("GENERATE PERFORMANCE REPORT", use_container_width=True):
                m = dashboard_metrics(loads_df)
                pdf = generate_performance_report_pdf(loads_df, m)
                st.session_state.perf_pdf = pdf
            if st.session_state.get("perf_pdf"):
                st.download_button(
                    "Download Report",
                    st.session_state.perf_pdf,
                    f"lp_dispatch_report_{date.today()}.pdf",
                    "application/pdf",
                    use_container_width=True,
                )

    with tab3:
        if loads_df.empty:
            st.info("Log a load first.")
        else:
            inv_options = {
                f"{r['bol_number']} — ${r['total_revenue']:,.0f}": r.to_dict()
                for _, r in loads_df.iterrows()
            }
            load = inv_options[st.selectbox("Invoice load", list(inv_options.keys()), key="inv_sel")]
            if st.button("GENERATE INVOICE PREVIEW", use_container_width=True):
                st.session_state.inv_pdf = generate_invoice_preview_pdf(load)
            if st.session_state.get("inv_pdf"):
                st.download_button(
                    "Download Invoice",
                    st.session_state.inv_pdf,
                    f"invoice_{load.get('bol_number', 'draft')}.pdf",
                    "application/pdf",
                    use_container_width=True,
                )


# ---------------------------------------------------------------------------
# Geofence Dispatch
# ---------------------------------------------------------------------------


def render_geofence_dispatch() -> None:
    render_page_header(
        "Geofence Dispatch",
        "Haversine arrival detection · visual alerts · yard & delivery zones",
    )
    st.caption(
        "WGS84 haversine distance in meters. Green = arrived · Amber = approaching · "
        "Red = outside."
    )

    st.markdown('<div class="lf-section-header">📡 Position</div>', unsafe_allow_html=True)
    preset_cols = st.columns(len(GEO_POSITION_PRESETS))
    preset_lat = st.session_state.get("geo_lat", GEO_POSITION_PRESETS["Spruce Pine Yard"][0])
    preset_lon = st.session_state.get("geo_lon", GEO_POSITION_PRESETS["Spruce Pine Yard"][1])
    for idx, (label, (plat, plon)) in enumerate(GEO_POSITION_PRESETS.items()):
        if preset_cols[idx].button(f"📍 {label}", use_container_width=True):
            st.session_state.geo_lat = plat
            st.session_state.geo_lon = plon
            st.rerun()

    g1, g2 = st.columns(2)
    lat = g1.number_input(
        "Your Latitude",
        value=float(st.session_state.get("geo_lat", preset_lat)),
        format="%.6f",
        key="geo_lat_input",
    )
    lon = g2.number_input(
        "Your Longitude",
        value=float(st.session_state.get("geo_lon", preset_lon)),
        format="%.6f",
        key="geo_lon_input",
    )
    st.session_state.geo_lat = lat
    st.session_state.geo_lon = lon

    if st.button("CHECK PROXIMITY", use_container_width=True, type="primary"):
        geofences_df = fetch_geofences()
        results = _enrich_geo_results(lat, lon, geofences_df)
        st.session_state.geo_results = results
        st.session_state.geo_checked_at = datetime.now().strftime("%I:%M %p")

    results = st.session_state.get("geo_results", [])
    checked = st.session_state.get("geo_checked_at", "")
    if results:
        st.markdown(
            f'<div class="lf-section-header">🎯 Arrival Alerts'
            f'{f" · checked {checked}" if checked else ""}</div>',
            unsafe_allow_html=True,
        )
        render_geofence_radar_summary(results)
        arrived = [r for r in results if r.get("zone") == "arrived"]
        for r in arrived[:2]:
            render_geofence_alert_banner(r)
        for r in results[:4]:
            render_geofence_proximity_card(r)

    st.markdown('<div class="lf-section-header">✅ Log Arrival</div>', unsafe_allow_html=True)
    loads_df = fetch_loads()
    load_options: dict[str, int | None] = {"(none)": None}
    if not loads_df.empty:
        for _, row in loads_df.head(15).iterrows():
            load_options[f"{row['bol_number']} — {row['shipper']}"] = int(row["id"])

    selected_load = st.selectbox("Link to load (optional)", list(load_options.keys()))
    load_id = load_options[selected_load]
    best = results[0] if results else None
    smart = smart_arrival_prefill(best.get("name", "") if best else "", load_id)
    st.markdown(
        '<div class="lf-section-header">🤖 Smart Arrival Suggestions</div>',
        unsafe_allow_html=True,
    )
    arrival_status = st.text_input("Suggested status", value=smart.get("status", "On Site"))
    arrival_notes = st.text_area("Pre-filled notes", value=smart.get("notes", ""))
    arrival_sms = st.text_area(
        "SMS draft (copy to SMS Alerts)",
        value=smart.get("sms_draft", ""),
        key="geo_sms_draft",
    )

    if st.button("LOG ARRIVAL", use_container_width=True, type="primary"):
        if not best:
            st.warning("Check proximity first.")
        elif best.get("zone") != "arrived":
            st.warning("Move inside the geofence (green zone) before logging arrival.")
        else:
            log_geofence_arrival(
                best.get("name", best.get("geofence_name", "Zone")),
                float(best.get("distance_m", 0)),
                lat,
                lon,
                load_id,
            )
            if load_id:
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                note_append = f"\n[{stamp}] {arrival_notes}"
                with closing(get_conn()) as conn:
                    conn.execute(
                        """
                        UPDATE loads SET notes = COALESCE(notes,'') || ? , status = ?
                        WHERE id = ?
                        """,
                        (note_append, arrival_status, load_id),
                    )
                    conn.commit()
            clear_cache()
            st.markdown(
                f'<div class="lp-alert-green pulse">🚛 ARRIVAL LOGGED — '
                f'{best.get("name", "")}</div>',
                unsafe_allow_html=True,
            )
            st.success(f"Arrival saved · status: {arrival_status}")
            if arrival_sms:
                st.info("SMS draft ready — open SMS Alerts tab to send or copy.")
            st.rerun()

    if results and results[0].get("zone") == "approaching":
        r0 = results[0]
        st.markdown(
            f'<div class="lp-alert-amber">Rolling toward {r0.get("name", "")} · '
            f'{r0.get("distance_m", 0):.0f}m out. Arrival logs when inside '
            f'{r0.get("radius_m", 0):.0f}m.</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="lf-section-header">📍 Active Geofences</div>', unsafe_allow_html=True)
    geofences_df = fetch_geofences()
    for _, g in geofences_df.iterrows():
        approach_m = float(g["radius_m"]) * GEOFENCE_APPROACH_MULTIPLIER
        st.markdown(
            f"""
            <div class="lf-panel" style="padding:0.85rem 1rem;margin-bottom:0.5rem;">
            <strong>{g['name']}</strong>
            <span class="lf-badge status">{g.get('geofence_type', 'Zone')}</span><br>
            <span style="color:#64748b;font-size:0.85rem;">
            {g.get('location_label', '')} · ({g['latitude']}, {g['longitude']}) ·
            {g['radius_m']:.0f}m arrive · {approach_m:.0f}m approach ring
            </span></div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="lf-section-header">🕐 Recent Arrivals</div>', unsafe_allow_html=True)
    events_df = fetch_geofence_events()
    if events_df.empty:
        st.info("No arrivals logged yet. Check proximity inside a zone, then tap LOG ARRIVAL.")
    else:
        for _, row in events_df.head(10).iterrows():
            render_geofence_event_card(row)


# ---------------------------------------------------------------------------
# SMS Alerts
# ---------------------------------------------------------------------------


def render_sms_alerts() -> None:
    render_page_header(
        "SMS Alert Generator",
        "One-tap dispatch messages · optional Twilio send",
    )
    st.warning(TWILIO_WARNING)

    leads = fetch_leads()
    lead_map = {row["company"]: row.to_dict() for _, row in leads.iterrows()} if not leads.empty else {}

    alert_type = st.selectbox(
        "Alert Type",
        ["arrival", "load update", "departure"],
        key="sms_alert_type",
    )
    selected = st.selectbox(
        "Select Lead",
        list(lead_map.keys()) if lead_map else ["—"],
        key="sms_lead_sel",
    )
    extra_default = st.session_state.get("geo_sms_draft", "")
    if alert_type == "departure":
        extra_default = extra_default or PRIMARY_LANE["origin"]
    extra = st.text_input(
        "Extra detail",
        value=extra_default,
        placeholder="e.g. On site, ready to load feldspar",
        key="sms_extra",
    )

    lead = lead_map.get(selected, {"company": "Contact", "phone": ""})
    sms_text = generate_sms_text(lead, alert_type, extra)
    if alert_type == "departure" and not st.session_state.get("geo_sms_draft"):
        sms_text = (
            f"L & P Dispatch: Departing {PRIMARY_LANE['origin']} with "
            f"{lead.get('company', 'shipper')} loaded end-dump. ETA per BOL. — Phillip"
        )

    st.text_area("Ready-to-copy SMS", sms_text, height=120, key="sms_preview")
    tc1, tc2, tc3 = st.columns(3)
    if tc1.button("COPY TEXT & LOG", use_container_width=True, type="primary"):
        log_sms(
            lead.get("id") if isinstance(lead.get("id"), int) else None,
            alert_type,
            sms_text,
            sent_via="clipboard",
        )
        st.session_state.sms_copied = True
        st.success("Logged to sms_log. Copy the text above and paste into your messaging app.")

    st.divider()
    st.subheader("Twilio Integration (optional)")
    st.caption("Credentials stored locally in app_settings table only.")
    tw1, tw2, tw3 = st.columns(3)
    tw_sid = tw1.text_input("Twilio SID", value=get_setting("twilio_sid"), key="twilio_sid")
    tw_token = tw2.text_input(
        "Twilio Token",
        value=get_setting("twilio_token"),
        type="password",
        key="twilio_token",
    )
    tw_from = tw3.text_input("From Number", value=get_setting("twilio_from"), key="twilio_from")
    if st.button("SAVE TWILIO SETTINGS", use_container_width=True):
        set_setting("twilio_sid", tw_sid.strip())
        set_setting("twilio_token", tw_token.strip())
        set_setting("twilio_from", tw_from.strip())
        st.success("Twilio credentials saved locally.")

    test_to = st.text_input("Test send to (E.164)", placeholder="+18285550123")
    if st.button("SEND TEST SMS VIA TWILIO", use_container_width=True):
        if not test_to.strip():
            st.error("Enter a test phone number.")
        else:
            try:
                sid = send_twilio_sms(test_to.strip(), sms_text)
                log_sms(None, alert_type, sms_text, sent_via="twilio", twilio_sid=sid)
                st.success(f"Sent — SID {sid}")
            except ImportError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("SMS Log")
    sms_df = fetch_sms_log()
    if sms_df.empty:
        st.info("No SMS messages logged yet.")
    else:
        st.dataframe(sms_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Telematics & Fuel
# ---------------------------------------------------------------------------


def render_telematics_fuel() -> None:
    render_page_header("Telematics & Fuel", "CSV import · IFTA prep · mileage tracking")
    tab1, tab2, tab3 = st.tabs(["Telematics Import", "Fuel Import", "IFTA Prep"])

    tel_cols = [
        "recorded_at",
        "odometer",
        "engine_hours",
        "latitude",
        "longitude",
        "speed_mph",
        "fuel_level_pct",
        "notes",
    ]
    fuel_cols = ["fill_date", "gallons", "cost", "odometer", "state", "vendor", "notes"]

    with tab1:
        st.caption(f"CSV columns: {', '.join(tel_cols)}")
        tel_file = st.file_uploader("Telematics CSV", type=["csv"], key="tel_upload")
        if tel_file and st.button("Import Telematics", use_container_width=True):
            df = pd.read_csv(tel_file)
            df.columns = [str(c).strip().lower() for c in df.columns]
            with closing(get_conn()) as conn:
                for _, row in df.iterrows():
                    conn.execute(
                        """
                        INSERT INTO telematics (
                            recorded_at, odometer, engine_hours, latitude,
                            longitude, speed_mph, fuel_level_pct, notes
                        ) VALUES (?,?,?,?,?,?,?,?)
                        """,
                        tuple(row.get(c) for c in tel_cols),
                    )
                conn.commit()
            clear_cache()
            st.success(f"Imported {len(df)} telematics rows.")

    with tab2:
        st.caption(f"CSV columns: {', '.join(fuel_cols)}")
        with st.form("manual_fuel_form"):
            f1, f2, f3 = st.columns(3)
            fill_date = f1.date_input("Fill date", value=date.today())
            gallons = f2.number_input("Gallons", min_value=0.0, value=100.0)
            cost = f3.number_input("Cost $", min_value=0.0, value=350.0)
            f4, f5 = st.columns(2)
            odometer = f4.number_input("Odometer", min_value=0.0, value=0.0)
            state = f5.text_input("State", value="NC")
            vendor = st.text_input("Vendor", value="Pilot")
            fuel_notes = st.text_area("Notes")
            if st.form_submit_button("LOG FUEL FILL", use_container_width=True):
                with closing(get_conn()) as conn:
                    conn.execute(
                        """
                        INSERT INTO fuel (
                            fill_date, gallons, cost, odometer, state, vendor, notes
                        ) VALUES (?,?,?,?,?,?,?)
                        """,
                        (
                            str(fill_date),
                            gallons,
                            cost,
                            odometer or None,
                            state,
                            vendor,
                            fuel_notes,
                        ),
                    )
                    conn.commit()
                clear_cache()
                st.success("Fuel entry logged.")
                st.rerun()

        fuel_file = st.file_uploader("Fuel CSV", type=["csv"], key="fuel_upload")
        if fuel_file and st.button("Import Fuel CSV", use_container_width=True):
            df = pd.read_csv(fuel_file)
            df.columns = [str(c).strip().lower() for c in df.columns]
            with closing(get_conn()) as conn:
                for _, row in df.iterrows():
                    conn.execute(
                        """
                        INSERT INTO fuel (
                            fill_date, gallons, cost, odometer, state, vendor, notes
                        ) VALUES (?,?,?,?,?,?,?)
                        """,
                        tuple(row.get(c) for c in fuel_cols),
                    )
                conn.commit()
            clear_cache()
            st.success(f"Imported {len(df)} fuel rows.")

    with tab3:
        fuel_df = fetch_fuel()
        if fuel_df.empty:
            st.info("Import fuel data to generate IFTA prep summary.")
        else:
            summary = ifta_summary(fuel_df)
            st.subheader("Gallons by State (IFTA prep)")
            st.dataframe(summary, use_container_width=True, hide_index=True)
            c1, c2 = st.columns(2)
            c1.metric("Total Gallons", f"{fuel_df['gallons'].sum():,.1f}")
            c2.metric("Total Fuel Cost", f"${fuel_df['cost'].sum():,.2f}")

        tel_df = fetch_telematics()
        if not tel_df.empty:
            st.subheader("Recent Telematics")
            st.dataframe(tel_df.head(15), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


def render_maintenance() -> None:
    render_page_header("Maintenance", "39ft end-dump · tractor · scheduled service")
    with st.form("maint_form"):
        c1, c2 = st.columns(2)
        asset = c1.selectbox("Asset", ASSET_OPTIONS)
        task = c2.text_input("Task *")
        c3, c4, c5 = st.columns(3)
        due = c3.date_input("Due Date", value=date.today() + timedelta(days=14))
        odometer = c4.number_input("Odometer", min_value=0.0, value=0.0)
        cost_est = c5.number_input("Est. Cost $", min_value=0.0, value=0.0)
        notes = st.text_area("Notes")
        if st.form_submit_button("SCHEDULE TASK", use_container_width=True):
            if not task.strip():
                st.error("Task description required.")
            else:
                with closing(get_conn()) as conn:
                    conn.execute(
                        """
                        INSERT INTO maintenance (
                            asset, task, due_date, odometer, cost, notes
                        ) VALUES (?,?,?,?,?,?)
                        """,
                        (asset, task.strip(), str(due), odometer or None, cost_est, notes),
                    )
                    conn.commit()
                clear_cache()
                st.success("Maintenance task scheduled.")
                st.rerun()

    maint_df = fetch_maintenance()
    if maint_df.empty:
        st.info("No maintenance tasks scheduled.")
    else:
        st.subheader("Scheduled & Completed")
        for _, row in maint_df.iterrows():
            col_a, col_b = st.columns([4, 1])
            with col_a:
                st.write(
                    f"**{row.get('asset', '')}** — {row.get('task', '')} · Due "
                    f"{row.get('due_date', '')} · {row.get('status', '')}"
                )
            with col_b:
                if row.get("status") != "Completed" and st.button(
                    "Done",
                    key=f"done_{row['id']}",
                    use_container_width=True,
                ):
                    with closing(get_conn()) as conn:
                        conn.execute(
                            """
                            UPDATE maintenance
                            SET status='Completed', completed_date=date('now')
                            WHERE id=?
                            """,
                            (int(row["id"]),),
                        )
                        conn.commit()
                    clear_cache()
                    st.rerun()
        st.dataframe(maint_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------


def render_compliance() -> None:
    render_page_header("Compliance", "Authority · insurance · inspections · IFTA")
    comp_df = fetch_compliance()
    if comp_df.empty:
        st.info("No compliance items.")
    else:
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

    with st.form("comp_add"):
        item = st.text_input("New item", key="comp_new_item")
        c1, c2 = st.columns(2)
        status = c1.selectbox("Status", COMPLIANCE_STATUSES)
        due = c2.date_input("Due date", value=date.today() + timedelta(days=90))
        notes = st.text_area("Notes")
        if st.form_submit_button("Add Item", use_container_width=True):
            if item.strip():
                with closing(get_conn()) as conn:
                    conn.execute(
                        "INSERT INTO compliance (item, status, due_date, notes) VALUES (?,?,?,?)",
                        (item.strip(), status, str(due), notes),
                    )
                    conn.commit()
                clear_cache()
                st.rerun()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def render_settings() -> None:
    render_page_header("Settings", "Display · export · privacy · nuclear delete")
    st.markdown(f'<div class="lp-privacy">{PRIVACY_NOTICE}</div>', unsafe_allow_html=True)
    ai_banner()

    st.subheader("Display — Road-Friendly")
    st.caption("≥52px touch targets · high contrast · night-driving mode for cab use.")
    night_on = st.toggle(
        "Night Driving Mode",
        value=is_night_mode(),
        help="Dark high-contrast theme — easier on eyes during night hauls.",
    )
    if night_on != is_night_mode():
        set_setting(NIGHT_MODE_KEY, "1" if night_on else "0")
        st.rerun()

    st.divider()
    st.subheader("Owner Role — Role-Aware Dashboard")
    role = st.selectbox(
        "Operating as",
        ["Phillip", "Lawson"],
        index=0 if get_owner_role() == "Phillip" else 1,
    )
    if role != get_owner_role():
        set_setting(OWNER_ROLE_KEY, role)
        st.rerun()

    st.divider()
    st.subheader("🎬 Demo Mode — 60-Second Sell")
    st.caption(
        "Seeds impressive loads, fuel, maintenance, and arrivals for partner demos."
    )
    if is_demo_mode():
        st.success("Demo mode ACTIVE — sample data loaded.")
    c1, c2 = st.columns(2)
    if c1.button("LOAD DEMO DATA", use_container_width=True, type="primary"):
        result = seed_demo_data(force=True)
        st.success(result.get("message", "Done."))
        st.rerun()
    if c2.button("EXIT DEMO MODE", use_container_width=True):
        set_setting(DEMO_MODE_KEY, "0")
        st.rerun()

    st.caption(
        f"v{APP_VERSION} Freight OS — feature manifest · SQLite: "
        f"{', '.join(FOUNDATION_TABLES)} · AI scoring · OCR · insights · "
        f"smart geofence · voice AI · demo mode · Reports (BOL/invoice) · "
        f"SMS/Twilio · bulk CSV/XLSX · Trailer: {TRAILER_PROFILE}"
    )

    st.divider()
    st.subheader("Legacy Data Migration")
    st.caption(
        "Auto-imports from ./lawson_freight.db and ./lp_freight.db into "
        "./lp_dispatch.db on first run. Legacy files are never deleted."
    )
    report_raw = get_setting(MIGRATION_REPORT_KEY)
    if report_raw:
        try:
            report = json.loads(report_raw)
            st.info(report.get("message", "Migration completed."))
            with st.expander("Migration details"):
                st.json(report)
        except json.JSONDecodeError:
            st.info("Migration report unavailable.")
    else:
        st.info("Migration runs automatically when the app starts.")
    if st.button("RE-RUN LEGACY MIGRATION", use_container_width=True):
        result = migrate_legacy_databases(force=True)
        st.success(result.get("message", "Migration finished."))
        st.rerun()

    st.divider()
    st.subheader("Twilio Credentials (optional)")
    st.caption("Stored locally in app_settings only. Leave blank to disable.")
    t1, t2, t3 = st.columns(3)
    tw_sid = t1.text_input("Twilio SID", value=get_setting("twilio_sid"), key="set_tw_sid")
    tw_token = t2.text_input(
        "Twilio Token",
        value=get_setting("twilio_token"),
        type="password",
        key="set_tw_token",
    )
    tw_from = t3.text_input("From Number", value=get_setting("twilio_from"), key="set_tw_from")
    if st.button("SAVE TWILIO CREDS", use_container_width=True):
        set_setting("twilio_sid", tw_sid.strip())
        set_setting("twilio_token", tw_token.strip())
        set_setting("twilio_from", tw_from.strip())
        st.success("Twilio credentials saved.")

    st.divider()
    st.subheader("Data Export")
    if st.button("EXPORT ALL DATA (ZIP)", use_container_width=True):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
            if DB_PATH.exists():
                zf.write(DB_PATH, "lp_dispatch.db")
            if ATTACHMENTS_DIR.exists():
                for f in ATTACHMENTS_DIR.rglob("*"):
                    if f.is_file():
                        zf.write(f, f"attachments/{f.name}")
        st.session_state.export_zip = buffer.getvalue()
    if st.session_state.get("export_zip"):
        stamp = datetime.now().strftime("%Y%m%d")
        st.download_button(
            "Download ZIP",
            st.session_state.export_zip,
            f"lp_dispatch_export_{stamp}.zip",
            "application/zip",
            use_container_width=True,
        )

    st.divider()
    st.subheader("Nuclear Delete")
    st.error(
        "Permanently deletes ./lp_dispatch.db and all ./attachments/. "
        "This cannot be undone. Phillip / Lawson owner-only action."
    )
    confirm = st.text_input("Type DELETE L&P to confirm")
    if st.button("NUCLEAR DELETE ALL LOCAL DATA", use_container_width=True):
        if confirm.strip().upper() == "DELETE L&P":
            nuclear_delete_all_data()
            st.warning("All local data wiped. Fresh database seeded.")
            st.rerun()
        else:
            st.error("Confirmation text did not match.")


# ---------------------------------------------------------------------------
# Delegates for load board / analytics (pass header + lane lambdas)
# ---------------------------------------------------------------------------


def render_load_board() -> None:
    render_load_board_page(
        get_conn=get_conn,
        clear_cache=clear_cache,
        commodity_options=COMMODITY_OPTIONS,
        primary_lane=PRIMARY_LANE,
        render_page_header=render_page_header,
        render_lane_banner=render_lane_banner,
    )


def render_analytics() -> None:
    render_analytics_page(
        fetch_loads=fetch_loads,
        render_page_header=render_page_header,
        commodity_options=COMMODITY_OPTIONS,
    )