"""
Lawson Freight Platform — merged 5-tab command center for L & P Dispatch.
Uses shared lp_dispatch.db (single source of truth). No separate lawson_freight.db.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from fpdf import FPDF

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "lp_dispatch.db"
ATTACHMENTS_DIR = BASE_DIR / "attachments"

TAB_OPTIONS = [
    "Dashboard",
    "Leads CRM",
    "Load Logger + Matcher",
    "Rate Calculator",
    "BOL Generator",
]

TARGET_LANE_ORIGIN = "Spruce Pine, NC"
TARGET_LANE_DESTINATION = "Central Georgia (Kohler area)"

PRIMARY_LANE = {
    "origin": TARGET_LANE_ORIGIN,
    "destination": TARGET_LANE_DESTINATION,
    "loaded_miles": 285,
    "baseline_rate_per_ton": 48.0,
}

TRAILER_MAX_TONS = 24
DEFAULT_LANE_MILES = 280
FUEL_COST_PER_MILE = 0.72
OPS_COST_PER_MILE = 0.18
DEFAULT_DEADHEAD_MILES = 285

LOAD_STATUS_OPTIONS = [
    "Potential",
    "Quoted",
    "Booked",
    "Logged",
    "Dispatched",
    "In Transit",
    "Delivered",
    "Paid",
]

HIGH_FIT_COMMODITIES = {
    "feldspar", "quartz", "mica", "kaolin", "silica sand", "spar", "clay",
    "industrial minerals", "aggregate", "crushed stone", "rock", "sand", "gravel",
}
MEDIUM_FIT_COMMODITIES = {"lime", "fertilizer", "kaolin"}
LOW_FIT_KEYWORDS = {
    "glass", "crushed glass", "slag", "hot", "liquid", "wet concrete",
    "asphalt", "hazmat", "corrosive", "steel", "rebar", "poultry litter",
}
WASHOUT_KEYWORDS = {"glass", "crushed glass", "slag", "asphalt", "fertilizer", "lime"}

APPROVED_COMMODITIES = [
    "Feldspar",
    "Quartz",
    "Mica",
    "Kaolin",
    "Silica Sand",
    "Industrial Minerals",
    "Aggregate",
    "Crushed Stone",
    "Spar",
    "Clay",
    "Rock",
    "Lime",
    "Fertilizer",
    "Other",
]

LEAD_STATUS_OPTIONS = [
    "New",
    "Contacted",
    "Quoted",
    "Hot",
    "Active",
    "Negotiating",
    "Closed",
]

CALL_TYPES = ["Outbound", "Inbound", "Follow-up", "Rate Quote"]
CALL_OUTCOMES = [
    "No answer",
    "Left voicemail",
    "Spoke — load offered",
    "Spoke — no load",
    "Callback scheduled",
]

SEED_LEADS = [
    {
        "company": "Sibelco Spruce Pine",
        "phone": "Main: 828-592-2780 | Quartz site: 828-592-2820",
        "lane_notes": "Highway 19E, Spruce Pine, NC 28777 — High-purity quartz + feldspar/mica byproducts",
        "commodity_focus": "Quartz, Feldspar, Mica",
        "status": "New",
        "priority": 1,
    },
    {
        "company": "Covia",
        "phone": "Industrial sales: 1-800-243-9004",
        "lane_notes": "7638 S Hwy 226, Spruce Pine, NC — Feldspar & minerals producer",
        "commodity_focus": "Feldspar, Minerals",
        "status": "New",
        "priority": 2,
    },
    {
        "company": "K-T Feldspar (The Quartz Corp)",
        "phone": "828-765-9621",
        "lane_notes": "8342 Hwy 226 N, Spruce Pine, NC 28777 — Key feldspar shipper",
        "commodity_focus": "Feldspar",
        "status": "New",
        "priority": 3,
    },
    {
        "company": "Feldspar Trucking (Trimac)",
        "phone": "828-765-7491",
        "lane_notes": "Local hauler — good intel source for backhauls",
        "commodity_focus": "Bulk / brokered",
        "status": "New",
        "priority": 4,
    },
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lane_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin TEXT,
            destination TEXT,
            commodity TEXT,
            base_rate_per_ton REAL,
            typical_distance_miles INTEGER,
            notes TEXT
        )
        """
    )

    for lead in SEED_LEADS:
        existing = cursor.execute(
            "SELECT id FROM leads WHERE company = ?",
            (lead["company"],),
        ).fetchone()
        if existing is None:
            cursor.execute(
                """
                INSERT INTO leads
                    (company, contact_name, phone, commodity_focus, lane_notes,
                     status, priority, created_at)
                VALUES (?, 'Dispatch', ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    lead["company"],
                    lead["phone"],
                    lead["commodity_focus"],
                    lead["lane_notes"],
                    lead["status"],
                    lead["priority"],
                ),
            )

    conn.commit()
    conn.close()


def fetch_leads() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM leads ORDER BY priority, company",
        conn,
    )
    conn.close()
    if not df.empty:
        df["notes"] = df["lane_notes"].fillna("")
    return df


def fetch_loads() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT *, pickup_date AS load_date
        FROM loads
        ORDER BY pickup_date DESC, id DESC
        """,
        conn,
    )
    conn.close()
    return df


def fetch_lane_rates() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM lane_rates ORDER BY origin, destination, commodity",
        conn,
    )
    conn.close()
    return df


def fetch_call_logs() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT c.*, l.company
        FROM call_logs c
        LEFT JOIN leads l ON c.lead_id = l.id
        ORDER BY c.logged_at DESC
        LIMIT 50
        """,
        conn,
    )
    conn.close()
    return df


def compute_dashboard_metrics(
    leads_df: pd.DataFrame, loads_df: pd.DataFrame
) -> dict[str, float | int]:
    hot_leads_contacted = 0
    if not leads_df.empty:
        hot_leads_contacted = int((leads_df["status"] != "New").sum())

    if loads_df.empty:
        return {
            "hot_leads_contacted": hot_leads_contacted,
            "loads_logged": 0,
            "pipeline_revenue": 0.0,
            "avg_rate_per_ton": 0.0,
        }

    pipeline_revenue = float(loads_df["total_revenue"].fillna(0).sum())
    total_tons = float(loads_df["weight_tons"].fillna(0).sum())
    if total_tons > 0:
        avg_rate_per_ton = pipeline_revenue / total_tons
    else:
        rates = loads_df["rate_per_ton"].dropna()
        avg_rate_per_ton = float(rates.mean()) if not rates.empty else 0.0

    return {
        "hot_leads_contacted": hot_leads_contacted,
        "loads_logged": len(loads_df),
        "pipeline_revenue": pipeline_revenue,
        "avg_rate_per_ton": avg_rate_per_ton,
    }


def calculate_rate(
    weight_tons: float,
    miles: float,
    loaded_miles: float | None = None,
    commodity: str = "",
) -> tuple[float, float]:
    base = PRIMARY_LANE["baseline_rate_per_ton"]
    lm = loaded_miles if loaded_miles and loaded_miles > 0 else miles
    loaded_share = lm / miles if miles > 0 else 1.0

    if loaded_share >= 0.95:
        multiplier = 1.05
    elif loaded_share >= 0.85:
        multiplier = 1.02
    elif loaded_share < 0.70:
        multiplier = 0.95
    else:
        multiplier = 1.0

    commodity_lower = commodity.lower()
    if any(c in commodity_lower for c in ("feldspar", "mica", "spar", "clay", "quartz")):
        multiplier *= 1.02
    elif "fertilizer" in commodity_lower:
        multiplier *= 1.03
    elif "lime" in commodity_lower:
        multiplier *= 1.01

    rate = round(base * multiplier, 2)
    revenue = round(rate * weight_tons, 2)
    return rate, revenue


def generate_bol_number() -> str:
    return f"LP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def generate_bol_pdf(load: dict) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Lawson Freight Platform", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Bill of Lading - Spruce Pine NC - 39ft frameless end-dump", ln=True)
    pdf.ln(4)

    rows = [
        ("BOL #", str(load.get("bol_number", "-"))),
        ("Date", str(load.get("pickup_date") or load.get("load_date") or date.today())),
        ("Shipper", str(load.get("shipper", "-"))),
        ("Commodity", str(load.get("commodity", "-"))),
        ("Origin", str(load.get("origin", TARGET_LANE_ORIGIN))),
        ("Destination", str(load.get("destination", "-"))),
        ("Weight (tons)", str(load.get("weight_tons", "-"))),
        ("Miles", str(load.get("miles", "-"))),
        ("Loaded Miles", str(load.get("loaded_miles", "-"))),
        ("Rate/Ton", f"${float(load.get('rate_per_ton', 0)):.2f}"),
        ("Total Revenue", f"${float(load.get('total_revenue', 0)):,.2f}"),
        ("Status", str(load.get("status", "Logged"))),
    ]
    pdf.set_font("Helvetica", "", 10)
    for label, value in rows:
        pdf.cell(45, 7, label, border=1)
        pdf.cell(0, 7, value, border=1, ln=True)

    notes = load.get("notes")
    if notes:
        pdf.ln(4)
        pdf.multi_cell(0, 6, f"Notes: {notes}")

    pdf.ln(8)
    pdf.cell(0, 7, "Shipper Signature: _________________________  Date: __________", ln=True)
    pdf.ln(6)
    pdf.cell(0, 7, "Driver Signature: _________________________  Date: __________", ln=True)
    pdf.ln(6)
    pdf.cell(0, 7, "Receiver Signature: _______________________  Date: __________", ln=True)

    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)


def bol_pdf_filename(load: dict) -> str:
    bol = str(load.get("bol_number", "DRAFT")).replace("/", "-").replace(" ", "_")
    pickup = str(load.get("pickup_date") or load.get("load_date") or date.today())[:10]
    return f"Lawson_BOL_{bol}_{pickup.replace('-', '')}.pdf"


def score_trailer_fit(commodity: str, weight: float, notes: str = "") -> dict[str, str | list[str]]:
    """Rule-based trailer fit for 39ft / 24-ton frameless end-dump."""
    reasons: list[str] = []
    commodity_lower = commodity.lower().strip()
    notes_lower = notes.lower()

    if weight > TRAILER_MAX_TONS:
        return {
            "level": "Low",
            "color": "red",
            "reasons": [f"Weight {weight:.1f}t exceeds {TRAILER_MAX_TONS}t rated capacity."],
        }

    if any(kw in commodity_lower or kw in notes_lower for kw in LOW_FIT_KEYWORDS):
        reasons.append("Commodity or notes flag compatibility concerns for a mineral end-dump.")
        if any(kw in commodity_lower or kw in notes_lower for kw in WASHOUT_KEYWORDS):
            reasons.append("Washout likely required before next fine/mineral load.")
        return {"level": "Low", "color": "red", "reasons": reasons}

    if commodity_lower == "other" or commodity_lower not in HIGH_FIT_COMMODITIES | MEDIUM_FIT_COMMODITIES:
        if commodity_lower == "other":
            reasons.append("Unspecified commodity — confirm tarp, lining, and washout rules.")
        else:
            reasons.append(f"{commodity} not on core approved list — verify before booking.")
        return {"level": "Medium", "color": "orange", "reasons": reasons}

    if commodity_lower in MEDIUM_FIT_COMMODITIES or "fertilizer" in commodity_lower:
        reasons.append("Acceptable with lined end-dump — confirm tarp and residue plan.")
        return {"level": "Medium", "color": "orange", "reasons": reasons}

    reasons.append("Core Spruce Pine mineral/aggregate fit for 39ft frameless end-dump.")
    if weight >= TRAILER_MAX_TONS * 0.9:
        reasons.append(f"Near capacity at {weight:.1f}t — confirm scale ticket.")
    return {"level": "High", "color": "green", "reasons": reasons}


def resolve_rate_and_revenue(
    weight: float,
    rate_per_ton: float | None,
    total_revenue: float | None,
    pricing_mode: str,
) -> tuple[float, float]:
    if weight <= 0:
        return 0.0, 0.0
    if pricing_mode == "Total revenue" and total_revenue and total_revenue > 0:
        return round(total_revenue / weight, 2), round(total_revenue, 2)
    if rate_per_ton and rate_per_ton > 0:
        return round(rate_per_ton, 2), round(rate_per_ton * weight, 2)
    if total_revenue and total_revenue > 0:
        return round(total_revenue / weight, 2), round(total_revenue, 2)
    return 0.0, 0.0


def commodity_rate_multiplier(commodity: str) -> float:
    commodity_lower = commodity.lower()
    if any(c in commodity_lower for c in ("feldspar", "mica", "spar", "clay", "quartz")):
        return 1.02
    if "fertilizer" in commodity_lower:
        return 1.03
    if "lime" in commodity_lower:
        return 1.01
    if commodity_lower == "other":
        return 1.0
    return 1.0


def compute_quote_metrics(
    weight: float,
    miles: float,
    deadhead_miles: float,
    rate_per_ton: float,
    commodity: str,
) -> dict[str, float | str]:
    revenue = round(rate_per_ton * weight, 2)
    rpm = revenue / miles if miles > 0 else 0.0
    deadhead_cost = round(deadhead_miles * (FUEL_COST_PER_MILE + OPS_COST_PER_MILE), 2)
    net_after_deadhead = round(revenue - deadhead_cost, 2)
    margin_pct = (net_after_deadhead / revenue) if revenue > 0 else 0.0

    base = PRIMARY_LANE["baseline_rate_per_ton"] * commodity_rate_multiplier(commodity)
    rate_low = round(base * 0.92, 2)
    rate_mid = round(base, 2)
    rate_high = round(base * 1.08, 2)

    return {
        "revenue": revenue,
        "rpm": rpm,
        "deadhead_cost": deadhead_cost,
        "net_after_deadhead": net_after_deadhead,
        "margin_pct": margin_pct,
        "rate_low": rate_low,
        "rate_mid": rate_mid,
        "rate_high": rate_high,
    }


def apply_load_prefill(prefill: dict) -> None:
    """Push Rate Calculator values into Load Logger widget session state."""
    if "pickup_date" in prefill:
        st.session_state.load_pickup_date = prefill["pickup_date"]
    if prefill.get("status") in LOAD_STATUS_OPTIONS:
        st.session_state.load_status = prefill["status"]
    if prefill.get("shipper_pick"):
        st.session_state.load_shipper_pick = prefill["shipper_pick"]
    if "shipper" in prefill:
        st.session_state.load_shipper_text = prefill["shipper"]
    if prefill.get("commodity") in APPROVED_COMMODITIES:
        st.session_state.load_commodity = prefill["commodity"]
    elif prefill.get("commodity"):
        st.session_state.load_commodity = "Other"
        st.session_state.load_commodity_other = prefill["commodity"]
    if "weight" in prefill:
        st.session_state.load_weight = float(prefill["weight"])
    if prefill.get("pricing_mode"):
        st.session_state.load_pricing_mode = prefill["pricing_mode"]
    if "rate_per_ton" in prefill:
        st.session_state.load_rate_per_ton = float(prefill["rate_per_ton"])
    if "total_revenue" in prefill:
        st.session_state.load_total_revenue = float(prefill["total_revenue"])
    if "destination" in prefill:
        st.session_state.load_destination = prefill["destination"]
    if "notes" in prefill:
        st.session_state.load_notes = prefill["notes"]
    if "miles" in prefill:
        st.session_state["_load_prefill_miles"] = float(prefill["miles"])
    if "loaded_miles" in prefill:
        st.session_state["_load_prefill_loaded_miles"] = float(prefill["loaded_miles"])


def prefill_load_logger(**kwargs) -> None:
    st.session_state.load_prefill = kwargs
    navigate_to_tab("Load Logger + Matcher")


def match_lane_rates(
    origin: str, destination: str, commodity: str, lane_rates_df: pd.DataFrame
) -> pd.DataFrame:
    if lane_rates_df.empty:
        return lane_rates_df

    matches = lane_rates_df.copy()
    matches["match_score"] = 0
    for idx, row in matches.iterrows():
        score = 0
        if str(row.get("origin", "")).lower() in origin.lower() or origin.lower() in str(row.get("origin", "")).lower():
            score += 2
        if str(row.get("destination", "")).lower() in destination.lower() or destination.lower() in str(row.get("destination", "")).lower():
            score += 2
        if str(row.get("commodity", "")).lower() == commodity.lower():
            score += 3
        elif commodity.lower() in str(row.get("commodity", "")).lower():
            score += 1
        matches.at[idx, "match_score"] = score

    return matches[matches["match_score"] > 0].sort_values("match_score", ascending=False)


def navigate_to_tab(tab_name: str) -> None:
    st.session_state.active_tab = tab_name
    st.session_state.main_navigation = tab_name
    st.rerun()


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Lawson Freight")
        st.markdown(
            "**Mission:** Build loaded miles Spruce Pine NC → Central Georgia "
            "(Kohler area). Minimize deadhead."
        )
        st.divider()
        st.subheader("Trailer Specs")
        st.markdown("- **Type:** 39 ft frameless end-dump")
        st.markdown("- **Rated capacity:** ~24 tons")
        st.divider()
        st.subheader("Approved Commodities")
        for commodity in APPROVED_COMMODITIES[:8]:
            st.markdown(f"- {commodity}")
        st.divider()
        st.caption(f"Database: `{DB_PATH.name}`")
        st.caption(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def render_target_lane_banner() -> None:
    lane_col1, lane_col2, lane_col3 = st.columns([2, 1, 2])
    with lane_col1:
        st.markdown(
            f"<div style='text-align:right;font-size:1.1rem;font-weight:700;'>"
            f"📍 {TARGET_LANE_ORIGIN}</div>",
            unsafe_allow_html=True,
        )
    with lane_col2:
        st.markdown(
            "<div style='text-align:center;font-size:1.4rem;font-weight:800;"
            "color:#e85d04;padding:0.25rem 0;'>➜ TARGET LANE ➜</div>",
            unsafe_allow_html=True,
        )
    with lane_col3:
        st.markdown(
            f"<div style='text-align:left;font-size:1.1rem;font-weight:700;'>"
            f"🏁 {TARGET_LANE_DESTINATION}</div>",
            unsafe_allow_html=True,
        )


def render_dashboard_tab() -> None:
    st.subheader("Dashboard")

    leads_df = fetch_leads()
    loads_df = fetch_loads()
    metrics = compute_dashboard_metrics(leads_df, loads_df)

    render_target_lane_banner()

    st.info(
        "**Mission:** Build loaded miles from Spruce Pine, NC to Central Georgia "
        "(Kohler area). Every empty mile is margin lost — prioritize backhauls, "
        "feldspar/quartz shippers on Hwy 19E & 226, and lane rates that cover "
        "fuel + deadhead."
    )

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric(
        "Hot Leads Contacted",
        metrics["hot_leads_contacted"],
        help="Leads with status other than New",
    )
    kpi2.metric("Total Loads Logged", metrics["loads_logged"])
    kpi3.metric("Pipeline Revenue", f"${metrics['pipeline_revenue']:,.0f}")
    kpi4.metric("Avg Rate per Ton", f"${metrics['avg_rate_per_ton']:.2f}")

    st.markdown("#### Quick Actions")
    action1, action2, action3, action4 = st.columns(4)
    if action1.button("Log New Call / Update Lead", use_container_width=True):
        navigate_to_tab("Leads CRM")
    if action2.button("Log Potential Load", use_container_width=True):
        navigate_to_tab("Load Logger + Matcher")
    if action3.button("Open Rate Calculator", use_container_width=True):
        navigate_to_tab("Rate Calculator")
    if action4.button("Generate BOL", use_container_width=True):
        navigate_to_tab("BOL Generator")

    st.divider()
    st.markdown("#### Recent Activity")

    activity_left, activity_right = st.columns(2)

    with activity_left:
        st.markdown("**Last 5 Loads**")
        if loads_df.empty:
            st.caption("No loads logged yet.")
        else:
            load_cols = [
                c
                for c in [
                    "load_date",
                    "shipper",
                    "commodity",
                    "weight_tons",
                    "total_revenue",
                    "status",
                ]
                if c in loads_df.columns
            ]
            st.dataframe(
                loads_df[load_cols].head(5),
                use_container_width=True,
                hide_index=True,
            )

    with activity_right:
        st.markdown("**Last 5 Lead Notes**")
        if leads_df.empty:
            st.caption("No leads in CRM.")
        else:
            notes_df = leads_df.copy()
            notes_df["notes"] = notes_df["notes"].fillna("").astype(str)
            notes_df = notes_df[notes_df["notes"].str.strip() != ""]
            if notes_df.empty:
                st.caption("No lead notes recorded yet.")
            else:
                sort_col = (
                    "last_contact"
                    if "last_contact" in notes_df.columns
                    else "created_at"
                )
                notes_df = notes_df.sort_values(sort_col, ascending=False, na_position="last")
                lead_activity = notes_df[["company", "status", "notes", sort_col]].head(5)
                lead_activity = lead_activity.rename(columns={sort_col: "last_updated"})
                st.dataframe(
                    lead_activity,
                    use_container_width=True,
                    hide_index=True,
                )


def render_leads_crm_tab() -> None:
    st.subheader("Leads CRM")
    st.caption("Log calls, update status, and track Spruce Pine shipper outreach.")

    leads_df = fetch_leads()
    if leads_df.empty:
        st.warning("No leads found. Database will seed hot leads on next refresh.")
        return

    st.markdown("#### All Leads")
    display_df = leads_df[
        [c for c in ["company", "phone", "commodity_focus", "status", "last_contact", "notes"] if c in leads_df.columns]
    ]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### Log New Call / Update Lead")

    lead_options = {
        f"{row['company']} (ID {row['id']})": int(row["id"])
        for _, row in leads_df.iterrows()
    }
    selected_label = st.selectbox("Select lead", list(lead_options.keys()))
    lead_id = lead_options[selected_label]
    lead_row = leads_df[leads_df["id"] == lead_id].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        new_status = st.selectbox(
            "Status",
            LEAD_STATUS_OPTIONS,
            index=LEAD_STATUS_OPTIONS.index(lead_row["status"])
            if lead_row["status"] in LEAD_STATUS_OPTIONS
            else 0,
        )
        call_type = st.selectbox("Call type", CALL_TYPES)
        outcome = st.selectbox("Outcome", CALL_OUTCOMES)
    with col2:
        st.markdown(f"**Phone:** {lead_row.get('phone', '—')}")
        st.markdown(f"**Commodity focus:** {lead_row.get('commodity_focus', '—')}")
        call_notes = st.text_area(
            "Call / update notes",
            value="",
            placeholder="Rate discussed, callback time, load potential…",
        )

    if st.button("Save Call & Update Lead", type="primary", use_container_width=True):
        conn = get_connection()
        cursor = conn.cursor()
        combined_notes = lead_row.get("notes") or lead_row.get("lane_notes") or ""
        if call_notes.strip():
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            combined_notes = f"{combined_notes}\n[{timestamp}] {call_notes}".strip()
        cursor.execute(
            """
            UPDATE leads
            SET status = ?, lane_notes = ?, last_contact = datetime('now')
            WHERE id = ?
            """,
            (new_status, combined_notes, lead_id),
        )
        cursor.execute(
            """
            INSERT INTO call_logs (lead_id, call_type, notes, outcome)
            VALUES (?, ?, ?, ?)
            """,
            (lead_id, call_type, call_notes, outcome),
        )
        conn.commit()
        conn.close()
        st.success(f"Updated {lead_row['company']} — status: {new_status}")
        st.rerun()

    st.divider()
    st.markdown("#### Recent Calls")
    calls_df = fetch_call_logs()
    if calls_df.empty:
        st.caption("No calls logged yet.")
    else:
        call_cols = [c for c in ["logged_at", "company", "call_type", "outcome", "notes"] if c in calls_df.columns]
        st.dataframe(calls_df[call_cols].head(10), use_container_width=True, hide_index=True)


def render_load_logger_tab() -> None:
    st.subheader("Load Logger + Matcher")
    render_target_lane_banner()

    prefill = st.session_state.pop("load_prefill", {})
    if prefill:
        apply_load_prefill(prefill)
        st.success("Rate Calculator values loaded — review and save when ready.")

    leads_df = fetch_leads()
    shipper_options = ["— Free text —"] + (
        leads_df["company"].tolist() if not leads_df.empty else []
    )

    commodity_options = list(APPROVED_COMMODITIES)
    prefill_commodity = prefill.get("commodity", "Feldspar")
    if prefill_commodity not in commodity_options:
        prefill_commodity = "Other"

    st.markdown("#### Log New Load")
    row1a, row1b = st.columns(2)
    pickup = row1a.date_input(
        "Date",
        value=prefill.get("pickup_date", date.today()),
        key="load_pickup_date",
    )
    load_status = row1b.selectbox(
        "Status",
        LOAD_STATUS_OPTIONS,
        index=LOAD_STATUS_OPTIONS.index(prefill.get("status", "Potential"))
        if prefill.get("status") in LOAD_STATUS_OPTIONS
        else 0,
        key="load_status",
    )

    row2a, row2b = st.columns(2)
    default_shipper_pick = prefill.get("shipper_pick", "— Free text —")
    if default_shipper_pick not in shipper_options:
        default_shipper_pick = "— Free text —"
    shipper_pick = row2a.selectbox(
        "Shipper",
        shipper_options,
        index=shipper_options.index(default_shipper_pick),
        key="load_shipper_pick",
    )
    commodity = row2b.selectbox(
        "Commodity",
        commodity_options,
        index=commodity_options.index(prefill_commodity),
        key="load_commodity",
    )

    shipper = ""
    if shipper_pick == "— Free text —":
        shipper = st.text_input(
            "Shipper name",
            value=prefill.get("shipper", ""),
            placeholder="Enter shipper / broker name",
            key="load_shipper_text",
        )
    else:
        shipper = shipper_pick

    commodity_final = commodity
    if commodity == "Other":
        commodity_final = st.text_input(
            "Specify commodity",
            value=prefill.get("commodity_other", prefill.get("commodity", "")),
            placeholder="e.g. Crushed glass (washout required)",
            key="load_commodity_other",
        )

    row3a, row3b, row3c = st.columns(3)
    weight = row3a.number_input(
        "Weight (tons)",
        min_value=0.0,
        max_value=30.0,
        value=float(prefill.get("weight", 24.0)),
        step=0.5,
        key="load_weight",
    )
    pricing_mode = row3b.selectbox(
        "Price by",
        ["Rate per ton", "Total revenue"],
        index=0 if prefill.get("pricing_mode", "Rate per ton") == "Rate per ton" else 1,
        key="load_pricing_mode",
    )
    if pricing_mode == "Rate per ton":
        rate_input = row3c.number_input(
            "Rate per ton ($)",
            min_value=0.0,
            value=float(prefill.get("rate_per_ton", PRIMARY_LANE["baseline_rate_per_ton"])),
            step=0.25,
            key="load_rate_per_ton",
        )
        revenue_input = 0.0
    else:
        revenue_input = row3c.number_input(
            "Total revenue ($)",
            min_value=0.0,
            value=float(prefill.get("total_revenue", 0.0)),
            step=1.0,
            key="load_total_revenue",
        )
        rate_input = 0.0

    destination = st.text_input(
        "Destination",
        value=prefill.get("destination", PRIMARY_LANE["destination"]),
        key="load_destination",
    )
    notes = st.text_area(
        "Notes",
        value=prefill.get("notes", ""),
        placeholder="Potential pickup window, tarp, washout, scale instructions…",
        key="load_notes",
    )

    preview_commodity = commodity_final or commodity
    rate_preview, revenue_preview = resolve_rate_and_revenue(
        weight, rate_input if pricing_mode == "Rate per ton" else None,
        revenue_input if pricing_mode == "Total revenue" else None,
        pricing_mode,
    )
    fit = score_trailer_fit(preview_commodity, weight, notes)

    st.markdown("#### Trailer Fit Score")
    fit_cols = st.columns([1, 3])
    level = fit["level"]
    if level == "High":
        fit_cols[0].success(f"**{level}**")
    elif level == "Medium":
        fit_cols[0].warning(f"**{level}**")
    else:
        fit_cols[0].error(f"**{level}**")
    fit_cols[1].markdown(
        " · ".join(fit["reasons"])
        + (f" · Est. **${rate_preview:.2f}/ton** · **${revenue_preview:,.0f}** total"
           if rate_preview > 0 else "")
    )

    submitted = st.button("Save Load", type="primary", use_container_width=True, key="save_load_btn")

    if submitted:
        if not shipper or not str(shipper).strip():
            st.error("Shipper is required.")
        elif not preview_commodity or not str(preview_commodity).strip():
            st.error("Commodity is required.")
        elif weight <= 0:
            st.error("Weight must be greater than zero.")
        elif rate_preview <= 0 or revenue_preview <= 0:
            st.error("Enter a valid rate per ton or total revenue.")
        elif weight > TRAILER_MAX_TONS:
            st.error(f"Weight exceeds {TRAILER_MAX_TONS}-ton trailer limit.")
        else:
            miles = float(
                st.session_state.get("_load_prefill_miles", DEFAULT_LANE_MILES)
            )
            loaded_miles = float(
                st.session_state.get("_load_prefill_loaded_miles", miles)
            )
            deadhead = max(0.0, miles - loaded_miles)
            bol = generate_bol_number()
            conn = get_connection()
            conn.execute(
                """
                INSERT INTO loads (
                    bol_number, shipper, commodity, weight_tons, miles,
                    loaded_miles, deadhead_miles, pickup_date, origin, destination,
                    rate_per_ton, total_revenue, notes, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bol,
                    shipper.strip(),
                    preview_commodity.strip(),
                    weight,
                    miles,
                    loaded_miles,
                    deadhead,
                    str(pickup),
                    PRIMARY_LANE["origin"],
                    destination,
                    rate_preview,
                    revenue_preview,
                    notes,
                    load_status,
                ),
            )
            conn.commit()
            conn.close()
            st.success(
                f"Load saved — {load_status} · BOL {bol} · "
                f"${revenue_preview:,.2f} · {level} trailer fit"
            )
            st.rerun()

    st.divider()
    st.markdown("#### Recent Logged Loads")
    loads_df = fetch_loads()
    if loads_df.empty:
        st.caption("No loads logged yet.")
    else:
        st.dataframe(
            loads_df[
                [
                    c
                    for c in [
                        "load_date",
                        "shipper",
                        "commodity",
                        "weight_tons",
                        "rate_per_ton",
                        "total_revenue",
                        "status",
                        "bol_number",
                    ]
                    if c in loads_df.columns
                ]
            ].head(15),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Lane Matcher (saved benchmarks)"):
        lane_rates_df = fetch_lane_rates()
        m1, m2, m3 = st.columns(3)
        match_origin = m1.text_input(
            "Match origin", value=PRIMARY_LANE["origin"], key="match_origin"
        )
        match_dest = m2.text_input(
            "Match destination", value=PRIMARY_LANE["destination"], key="match_dest"
        )
        match_commodity = m3.selectbox(
            "Match commodity", commodity_options, key="match_commodity"
        )
        matches = match_lane_rates(
            match_origin, match_dest, match_commodity, lane_rates_df
        )
        if lane_rates_df.empty:
            st.info("No lane rates on file yet.")
        elif matches.empty:
            st.warning("No matches for this lane/commodity.")
        else:
            st.dataframe(matches, use_container_width=True, hide_index=True)


def render_rate_calculator_tab() -> None:
    st.subheader("Rate Calculator")
    st.caption("Quick quoting for calls — Spruce Pine → Central GA lane")

    lane1, lane2 = st.columns(2)
    origin = lane1.text_input("Origin", value=PRIMARY_LANE["origin"], key="quote_origin")
    destination = lane2.text_input(
        "Destination", value=PRIMARY_LANE["destination"], key="quote_destination"
    )

    q1, q2, q3 = st.columns(3)
    commodity = q1.selectbox("Commodity", APPROVED_COMMODITIES, key="quote_commodity")
    weight = q2.number_input(
        "Estimated weight (tons)", min_value=0.0, value=24.0, step=0.5, key="quote_weight"
    )
    lane_miles = q3.number_input(
        "One-way miles",
        min_value=1.0,
        value=float(DEFAULT_LANE_MILES),
        step=5.0,
        key="quote_miles",
        help="Default ~280 mi for Spruce Pine → Kohler area",
    )

    rate_mode = st.radio(
        "Quote using",
        ["Rate per ton", "Revenue per mile (RPM)"],
        horizontal=True,
        key="quote_rate_mode",
    )

    r1, r2 = st.columns(2)
    if rate_mode == "Rate per ton":
        input_rate = r1.number_input(
            "Target rate per ton ($)",
            min_value=0.0,
            value=float(PRIMARY_LANE["baseline_rate_per_ton"]),
            step=0.25,
            key="quote_rpt",
        )
        input_rpm = (input_rate * weight / lane_miles) if lane_miles > 0 and weight > 0 else 0.0
        r2.metric("Implied RPM", f"${input_rpm:.2f}/mi")
    else:
        input_rpm = r1.number_input(
            "Target RPM ($/loaded mile)",
            min_value=0.0,
            value=4.35,
            step=0.05,
            key="quote_rpm",
        )
        input_rate = (input_rpm * lane_miles / weight) if weight > 0 else 0.0
        r2.metric("Implied rate/ton", f"${input_rate:.2f}")

    deadhead_miles = st.number_input(
        "Est. deadhead miles (return empty)",
        min_value=0.0,
        value=float(DEFAULT_DEADHEAD_MILES),
        step=5.0,
        key="quote_deadhead",
    )

    metrics = compute_quote_metrics(weight, lane_miles, deadhead_miles, input_rate, commodity)
    fit = score_trailer_fit(commodity, weight, "")

    st.divider()
    st.markdown("#### Quote Summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Est. total revenue", f"${metrics['revenue']:,.0f}")
    m2.metric("Revenue per mile", f"${metrics['rpm']:.2f}")
    m3.metric("Deadhead cost est.", f"${metrics['deadhead_cost']:,.0f}")
    m4.metric("Net after deadhead", f"${metrics['net_after_deadhead']:,.0f}")

    st.caption(
        f"Deadhead formula: {deadhead_miles:.0f} mi × "
        f"${FUEL_COST_PER_MILE + OPS_COST_PER_MILE:.2f}/mi "
        f"(fuel ${FUEL_COST_PER_MILE:.2f} + ops ${OPS_COST_PER_MILE:.2f}) · "
        f"Margin after deadhead: {metrics['margin_pct']:.0%}"
    )

    if metrics["net_after_deadhead"] < 0:
        st.error("Quoted revenue does not cover estimated deadhead — raise rate or find a backhaul.")
    elif metrics["margin_pct"] < 0.35:
        st.warning("Thin margin after deadhead — confirm fuel and tarp/washout costs.")
    else:
        st.success("Quote clears deadhead with workable margin for a single-truck lane.")

    st.markdown("#### Recommended rate range (this lane / commodity)")
    range_cols = st.columns(3)
    range_cols[0].metric("Floor", f"${metrics['rate_low']:.2f}/ton")
    range_cols[1].metric("Target", f"${metrics['rate_mid']:.2f}/ton")
    range_cols[2].metric("Ceiling", f"${metrics['rate_high']:.2f}/ton")
    st.caption(
        f"Trailer fit: **{fit['level']}** — {fit['reasons'][0] if fit['reasons'] else ''}"
    )

    if st.button("Use these numbers to log a load", type="primary", use_container_width=True):
        prefill_load_logger(
            pickup_date=date.today(),
            shipper_pick="— Free text —",
            shipper="",
            commodity=commodity,
            weight=weight,
            rate_per_ton=round(input_rate, 2),
            total_revenue=metrics["revenue"],
            pricing_mode="Rate per ton",
            status="Quoted",
            destination=destination,
            miles=lane_miles,
            loaded_miles=lane_miles,
            notes=(
                f"Quoted {origin} → {destination} · {lane_miles:.0f} mi · "
                f"${metrics['rpm']:.2f}/mi · deadhead est ${metrics['deadhead_cost']:,.0f}"
            ),
        )

    st.divider()
    with st.expander("Save benchmark to lane_rates"):
        with st.form("save_lane_rate"):
            lane_notes = st.text_input("Lane notes", value=f"Quoted {date.today()}")
            save_submitted = st.form_submit_button("Save Lane Rate", use_container_width=True)
        if save_submitted:
            conn = get_connection()
            conn.execute(
                """
                INSERT INTO lane_rates
                    (origin, destination, commodity, base_rate_per_ton,
                     typical_distance_miles, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    origin,
                    destination,
                    commodity,
                    round(input_rate, 2),
                    int(lane_miles),
                    lane_notes,
                ),
            )
            conn.commit()
            conn.close()
            st.success(f"Saved ${input_rate:.2f}/ton benchmark for {origin} → {destination}")
            st.rerun()

    lane_rates_df = fetch_lane_rates()
    if not lane_rates_df.empty:
        st.markdown("#### Saved Lane Rates")
        st.dataframe(lane_rates_df, use_container_width=True, hide_index=True)


def render_bol_generator_tab() -> None:
    st.subheader("BOL Generator")
    st.caption("Generate printable PDF Bills of Lading from logged loads.")

    loads_df = fetch_loads()
    if loads_df.empty:
        st.info("No loads logged yet. Log a load in **Load Logger + Matcher** first.")
        return

    options = {
        f"{row['bol_number']} — {row['shipper']} ({row.get('load_date', '')})": row.to_dict()
        for _, row in loads_df.iterrows()
    }
    selected_key = st.selectbox("Select load", list(options.keys()))
    load = options[selected_key]

    preview1, preview2 = st.columns(2)
    with preview1:
        st.markdown(f"**Shipper:** {load.get('shipper', '—')}")
        st.markdown(f"**Commodity:** {load.get('commodity', '—')}")
        st.markdown(f"**Weight:** {load.get('weight_tons', '—')} tons")
    with preview2:
        st.markdown(f"**Route:** {load.get('origin', TARGET_LANE_ORIGIN)} → {load.get('destination', '—')}")
        st.markdown(f"**Revenue:** ${float(load.get('total_revenue', 0)):,.2f}")
        st.markdown(f"**Status:** {load.get('status', 'Logged')}")

    pdf_name = bol_pdf_filename(load)

    if st.button("Generate PDF BOL", type="primary", use_container_width=True):
        try:
            pdf_bytes = generate_bol_pdf(load)
            st.session_state["bol_pdf_bytes"] = pdf_bytes
            st.session_state["bol_pdf_name"] = pdf_name
            out_path = ATTACHMENTS_DIR / pdf_name
            out_path.write_bytes(pdf_bytes)
            st.success(f"BOL generated — saved to attachments/{pdf_name}")
        except Exception as exc:
            st.error(f"BOL generation failed: {exc}")

    if (
        st.session_state.get("bol_pdf_bytes")
        and st.session_state.get("bol_pdf_name") == pdf_name
    ):
        st.download_button(
            "Download PDF BOL",
            st.session_state["bol_pdf_bytes"],
            pdf_name,
            mime="application/pdf",
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(
        page_title="Lawson Freight Platform",
        page_icon="🚛",
        layout="wide",
    )

    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Dashboard"

    if not DB_PATH.exists():
        st.error(
            f"`{DB_PATH}` not found. Run the main L & P Freight app once (`run.ps1`) "
            "to initialize lp_dispatch.db, then relaunch this app."
        )
        st.stop()

    try:
        from lp_helpers.database import init_db
        from lp_helpers.ui_components import inject_road_css, render_day_night_toggle

        init_db()
        with st.sidebar:
            st.markdown('<div class="nav-group-label">Display</div>', unsafe_allow_html=True)
            render_day_night_toggle()
        inject_road_css()
    except ImportError:
        init_database()
        render_sidebar()
    else:
        init_database()

    st.title("Lawson Freight Platform")
    st.caption("Spruce Pine, NC — 39ft frameless end-dump command center · shared lp_dispatch.db")

    selected_tab = st.radio(
        "Navigation",
        TAB_OPTIONS,
        horizontal=True,
        label_visibility="collapsed",
        index=TAB_OPTIONS.index(st.session_state.active_tab),
        key="main_navigation",
    )
    st.session_state.active_tab = selected_tab

    if selected_tab == "Dashboard":
        render_dashboard_tab()
    elif selected_tab == "Leads CRM":
        render_leads_crm_tab()
    elif selected_tab == "Load Logger + Matcher":
        render_load_logger_tab()
    elif selected_tab == "Rate Calculator":
        render_rate_calculator_tab()
    elif selected_tab == "BOL Generator":
        render_bol_generator_tab()


if __name__ == "__main__":
    main()