import streamlit as st
import sqlite3
from datetime import datetime, date, timedelta
import pandas as pd
from fpdf import FPDF

from lp_helpers.database import DB_PATH, init_db, seed_assets
from lp_helpers.pay_engine import pay_decision
from routing_editor import ingest_eld_miles
from lp_helpers.ui_theme import inject_mobile_css, render_bottom_nav, SCREENS, empty_state
from lp_helpers.fleet import get_fleet_view
from lp_helpers.notifications import get_notifications, dismiss_notification, CATEGORY_META
from lp_helpers.driver import get_driver_hos, get_driver_loads, accept_load, save_bol_photo
from lp_helpers.billing import generate_invoice_pdf, fetch_load, mark_invoice_sent
from lp_helpers.recommend import get_recommendations

st.set_page_config(page_title="L & P Freight", layout="centered", page_icon="🚛", initial_sidebar_state="collapsed")

# Mobile-first native-app theme
st.markdown('<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">', unsafe_allow_html=True)
inject_mobile_css()
st.session_state.setdefault("screen", "Dashboard")


def get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


from portal import (
    add_po_load,
    create_purchase_order,
    fetch_customers,
    fetch_po_loads,
    fetch_purchase_orders,
    get_customer_po_summary,
    init_customer_portal,
    seed_demo_customers,
    update_po_load_status,
    update_po_status,
)

def fetch_assets():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM assets ORDER BY name", conn)
    conn.close()
    return df

def fetch_settlements():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT s.*, l.bol_number, l.shipper, l.commodity, a.name as asset_name
        FROM settlements s
        LEFT JOIN loads l ON s.load_id = l.id
        LEFT JOIN assets a ON s.asset_id = a.id
        ORDER BY s.created_at DESC
    """, conn)
    conn.close()
    return df

def fetch_routes(load_id=None):
    conn = get_conn()
    q = "SELECT * FROM routes"
    params = ()
    if load_id is not None:
        q += " WHERE load_id = ?"
        params = (load_id,)
    q += " ORDER BY created_at DESC"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df

def save_route(load_id, waypoints, planned_loaded, planned_empty, google_miles=None, source='planned', notes=''):
    conn = get_conn()
    if google_miles is None and planned_loaded and planned_empty:
        google_miles = round(planned_loaded + planned_empty, 1)
    conn.execute(
        """
        INSERT INTO routes (load_id, waypoints, planned_loaded_miles, planned_empty_miles, google_miles, source, notes, updated_at)
        VALUES (?,?,?,?,?,?,?,datetime('now'))
        """,
        (load_id, waypoints, planned_loaded, planned_empty, google_miles, source, notes)
    )
    conn.commit()
    conn.close()

def update_route_actuals(route_id, actual_loaded, actual_empty):
    conn = get_conn()
    conn.execute(
        """
        UPDATE routes SET actual_loaded_miles = ?, actual_empty_miles = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (actual_loaded, actual_empty, route_id)
    )
    conn.commit()
    conn.close()

def calcpay(loaded_miles, empty_miles, loaded_rate, empty_rate, bonuses=0.0, deductions=0.0, accessorials=0.0):
    total = (loaded_miles * loaded_rate) + (empty_miles * empty_rate) + bonuses + accessorials - deductions
    return round(total, 2)

def route_variance_analysis(planned_total, actual_total, google_miles=None, tolerance_pct=10.0):
    if planned_total <= 0 and (not google_miles or google_miles <= 0):
        return {'pay_basis': 'actual', 'variance_pct': 0.0, 'flagged': False, 'basis_miles': actual_total}
    basis = google_miles if google_miles and google_miles > 0 else planned_total
    if actual_total > 0 and basis > 0:
        var = ((actual_total - basis) / basis) * 100.0
    else:
        var = 0.0
    flagged = abs(var) > tolerance_pct
    return {'pay_basis': 'actual' if flagged else 'planned', 'variance_pct': round(var, 1), 'flagged': flagged, 'basis_miles': basis}

def variance_pct(planned_total, actual_total):
    if planned_total <= 0:
        return 0.0
    return round((actual_total - planned_total) / planned_total * 100, 1)

def settlement_pdf(s, load, asset_name=""):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "L & P Freight — Settlement Statement", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Load Details", ln=True)
    pdf.set_font("Helvetica", "", 10)
    rows = [
        ("BOL #", str(load.get('bol_number', '-'))),
        ("Shipper", str(load.get('shipper', '-'))),
        ("Driver", str(s.get('driver_name', '-'))),
        ("Asset", str(asset_name or '-')),
        ("Commodity", str(load.get('commodity', '-'))),
    ]
    for label, value in rows:
        pdf.cell(45, 7, label, border=1)
        pdf.cell(0, 7, value, border=1, ln=True)
    
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Mileage & Pay", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pay_rows = [
        ("Planned Loaded", f"{s['planned_loaded_miles']:.0f} mi"),
        ("Actual Loaded", f"{s['actual_loaded_miles']:.0f} mi"),
        ("Loaded Rate", f"${s['loaded_rate']:.2f}/mi"),
        ("Loaded Pay", f"${s['actual_loaded_miles'] * s['loaded_rate']:.2f}"),
        ("Planned Empty", f"{s['planned_empty_miles']:.0f} mi"),
        ("Actual Empty", f"{s['actual_empty_miles']:.0f} mi"),
        ("Empty Rate", f"${s['empty_rate']:.2f}/mi"),
        ("Empty Pay", f"${s['actual_empty_miles'] * s['empty_rate']:.2f}"),
        ("Bonuses", f"${s['bonuses']:.2f}"),
        ("Accessorials", f"${s['accessorials']:.2f}"),
        ("Deductions", f"-${s['deductions']:.2f}"),
    ]
    for label, value in pay_rows:
        pdf.cell(55, 7, label, border=1)
        pdf.cell(0, 7, value, border=1, ln=True)
    
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, f"TOTAL PAY: ${s['total_pay']:.2f}", ln=True)
    if s.get('variance_pct') is not None:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, f"Route Variance: {s['variance_pct']:.1f}%", ln=True)
    
    pdf.ln(8)
    pdf.cell(0, 7, "Driver Signature: _________________________  Date: __________", ln=True)
    pdf.ln(6)
    pdf.cell(0, 7, "Dispatcher Signature: _____________________  Date: __________", ln=True)
    
    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)

def invoice_preview_pdf(load):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "L & P Freight — Invoice Preview", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
    pdf.ln(4)
    total_miles = (load.get('loaded_miles', 0) or 0) + (load.get('deadhead_miles', 0) or 0)
    rows = [
        ("To", str(load.get('shipper', '-'))),
        ("BOL #", str(load.get('bol_number', '-'))),
        ("Origin", "Spruce Pine, NC"),
        ("Destination", "Central Georgia (Kohler)"),
        ("Commodity", str(load.get('commodity', '-'))),
        ("Weight", f"{load.get('weight_tons', 0)} tons"),
        ("Miles", f"{total_miles:.0f} mi"),
        ("Rate/Ton", f"${load.get('rate_per_ton', 0):.2f}"),
        ("Total", f"${load.get('total_revenue', 0):.2f}"),
    ]
    for label, value in rows:
        pdf.cell(45, 7, label, border=1)
        pdf.cell(0, 7, value, border=1, ln=True)
    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)


def bol_pdf(bol_number, shipper, commodity, weight_tons, rate_per_ton, origin="Spruce Pine, NC", destination="Central Georgia (Kohler area)", pickup_date=None, notes=""):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "L & P Freight - Bill of Lading", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Spruce Pine NC - 39ft frameless lined end-dump", ln=True)
    pdf.ln(4)
    rows = [
        ("BOL #", str(bol_number)),
        ("Date", str(pickup_date or date.today())),
        ("Shipper", str(shipper or "-")),
        ("Commodity", str(commodity or "-")),
        ("Origin", str(origin)),
        ("Destination", str(destination)),
        ("Weight (tons)", f"{weight_tons:.1f}"),
        ("Rate/Ton", f"${rate_per_ton:.2f}"),
        ("Total Revenue", f"${weight_tons * rate_per_ton:,.2f}"),
    ]
    for label, value in rows:
        pdf.cell(45, 7, label, border=1)
        pdf.cell(0, 7, value, border=1, ln=True)
    if notes:
        pdf.ln(4)
        pdf.multi_cell(0, 6, f"Notes: {notes}")
    pdf.ln(8)
    pdf.cell(0, 7, "Shipper Signature: _________________________  Date: __________", ln=True)
    pdf.ln(6)
    pdf.cell(0, 7, "Driver Signature: __________________________  Date: __________", ln=True)
    pdf.ln(6)
    pdf.cell(0, 7, "Receiver Signature: ________________________  Date: __________", ln=True)
    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)


st.title("🚛 L & P Freight — Mobile Command Center")
st.caption("Spruce Pine NC → Central Georgia (Kohler area)  |  v3.2 — Billing & Driver Pay")

init_db()
seed_assets()
init_customer_portal()
seed_demo_customers()

# TOP APP BAR (mobile)
_unread = get_notifications()["unread"]
st.markdown(
    f"""
    <div class="lf-topbar">
        <div>
            <div class="lf-topbar-brand">L &amp; P <span>Freight</span></div>
            <div class="lf-topbar-sub">Spruce Pine NC → Central Georgia</div>
        </div>
        <div class="lf-topbar-right">
            Local Command Center<br><b>v3.2</b><br>
            <span class="lf-pill {'red' if _unread else 'green'}"><span class="lf-dot"></span>{_unread} alert{'s' if _unread != 1 else ''}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Bottom-nav screen switching (mobile-first)
screen = st.session_state["screen"]

# ========== DASHBOARD ==========
if screen == "Dashboard":
    st.markdown(
        """
        <div class="lf-trailer-chip">
            <div class="type">Power Unit</div>
            <div class="spec">39 ft / 24-ton Frameless Lined End-Dump</div>
            <div class="lf-trailer-sub">Maximize loaded miles • Minimize deadhead</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
# ========== DASHBOARD ==========
if screen == "Dashboard":
    st.markdown('<div class="lf-page-title">Today’s Snapshot</div>', unsafe_allow_html=True)
    st.caption("Your operational command center")
    
    conn = get_conn()
    leads_df = pd.read_sql("SELECT * FROM leads", conn)
    loads_df = pd.read_sql("SELECT * FROM loads", conn)
    conn.close()
    
    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Hot Leads Contacted", len(leads_df[leads_df['status'] != 'New']))
    with col2:
        st.metric("Total Loads Logged", len(loads_df))
    with col3:
        revenue = loads_df['total_revenue'].sum() if not loads_df.empty else 0
        st.metric("Pipeline Revenue", f"${revenue:,.0f}")
    with col4:
        avg_rate = loads_df['rate_per_ton'].mean() if not loads_df.empty else 0
        st.metric("Avg Rate per Ton", f"${avg_rate:.2f}")
    
    # Deadhead Summary
    if not loads_df.empty:
        total_loaded = loads_df['loaded_miles'].fillna(0).sum()
        total_empty = loads_df['deadhead_miles'].fillna(0).sum()
        deadhead_pct = round((total_empty / (total_loaded + total_empty) * 100), 1) if (total_loaded + total_empty) > 0 else 0
        
        st.info(f"**Deadhead Tracking:** {total_empty:,.0f} empty miles logged  •  {deadhead_pct}% of total miles")
    
    # AI Copilot — contextual, actionable suggestions
    st.markdown('<div class="lf-section">🤖 AI Copilot</div>', unsafe_allow_html=True)
    recs = get_recommendations()
    if not recs:
        st.success("All clear — no actionable suggestions right now.")
    for rec in recs[:4]:
        st.markdown(
            f'<div class="lf-suggest-card {rec["severity"]}">'
            f'<b>{rec["title"]}</b><br><span style="font-size:0.85rem;">{rec["detail"]}</span></div>',
            unsafe_allow_html=True,
        )
        st.button(
            rec["cta"], key=f"rec_{rec['id']}", use_container_width=True, type="secondary",
            on_click=lambda s=rec["screen"]: st.session_state.update(screen=s),
        )
    
    # Follow-up Queue
    st.subheader("📅 Follow-up Queue (Automated)")
    today = date.today()
    due_leads = leads_df[
        (leads_df['next_followup_date'].notna()) & 
        (leads_df['next_followup_date'] != '') &
        (leads_df['status'].isin(['New', 'Contacted', 'Quote Sent']))
    ]
    
    if not due_leads.empty:
        st.warning(f"**{len(due_leads)} leads require follow-up**")
        st.dataframe(due_leads[['company', 'phone', 'status', 'next_followup_date', 'followup_type']], use_container_width=True, hide_index=True)
    else:
        st.success("No follow-ups due today. Excellent discipline.")
    
    # Recent Activity
    if not loads_df.empty:
        st.subheader("Recent Loads")
        st.dataframe(loads_df[['pickup_date', 'commodity', 'weight_tons', 'loaded_miles', 'deadhead_miles', 'total_revenue']].tail(5), use_container_width=True)

# ========== LEADS & FOLLOW-UPS ==========
if screen == "Leads":
    st.markdown('<div class="lf-page-title">Leads &amp; Follow-ups</div>', unsafe_allow_html=True)
    st.caption("Call the hot shippers — book the loads")
    st.subheader("Leads CRM + Automated Follow-up Sequences")
    
    conn = get_conn()
    leads_df = pd.read_sql("SELECT * FROM leads", conn)
    conn.close()
    
    st.dataframe(leads_df[['company', 'phone', 'status', 'last_contact', 'next_followup_date', 'followup_type']], use_container_width=True, hide_index=True)
    
    st.divider()
    st.subheader("Update Lead & Set Next Follow-up")
    
    selected = st.selectbox("Select Lead", leads_df['company'].tolist())
    row = leads_df[leads_df['company'] == selected].iloc[0]
    
    status_options = ["New", "Contacted", "Quote Sent", "Booked", "On Hold", "Not Interested", "Hot", "Active", "Negotiating", "Closed"]
    current_status = row['status'] if row['status'] in status_options else status_options[0]
    new_status = st.selectbox("Status", status_options, index=status_options.index(current_status))
    
    new_note = st.text_area("Call / Note Summary")
    
    colf1, colf2 = st.columns(2)
    with colf1:
        next_date = st.date_input("Next Follow-up Date", value=date.today() + timedelta(days=2))
    with colf2:
        f_type = st.selectbox("Follow-up Method", ["Phone Call", "Text", "Email", "Send Quote"])
    
    if st.button("Save Update & Schedule Follow-up"):
        conn = get_conn()
        c = conn.cursor()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        prior_notes = row['notes'] if pd.notna(row['notes']) else ""
        combined = f"[{ts}] {new_note}\n{prior_notes}" if new_note else prior_notes
        c.execute("""UPDATE leads SET status=?, notes=?, last_contact=?, next_followup_date=?, followup_type=? WHERE id=?""",
                  (new_status, combined, ts, str(next_date), f_type, int(row['id'])))
        conn.commit()
        conn.close()
        st.success("Lead updated and follow-up scheduled.")
        st.rerun()

# ========== LOG LOAD + DEADHEAD ==========
if screen == "Log Load":
    st.markdown('<div class="lf-page-title">Log Load + Deadhead</div>', unsafe_allow_html=True)
    st.caption("Capture the haul, the miles, and the money")
    st.subheader("Log Load + Track Empty Return Miles")
    
    conn = get_conn()
    leads = pd.read_sql("SELECT id, company FROM leads", conn)
    conn.close()
    
    lead_map = {r['company']: r['id'] for _, r in leads.iterrows()}
    sel_lead = st.selectbox("Shipper", list(lead_map.keys()))
    lead_id = lead_map[sel_lead]
    
    c1, c2 = st.columns(2)
    with c1:
        l_date = st.date_input("Load Date", value=date.today())
        comm = st.selectbox("Commodity", ["Feldspar","Mica","Spar","Clay","Rock (under 5 inches)","Lime","Fertilizer","Corn","Soybean","Urea","DAP","Crushed Glass (with washout)","Turkish Feldspar"])
        wgt = st.number_input("Weight (tons)", 1.0, 24.0, 22.0, 0.5)
    with c2:
        rate = st.number_input("Rate per Ton ($)", 20.0, 150.0, 55.0, 1.0)
        st.metric("Revenue", f"${wgt * rate:,.2f}")
    
    # Deadhead inputs
    dm1, dm2 = st.columns(2)
    with dm1:
        loaded_mi = st.number_input("Loaded Miles", 100, 400, 280, 10)
    with dm2:
        empty_mi = st.number_input("Empty Return Miles (Deadhead)", 0, 400, 280, 10)
    
    total_mi = loaded_mi + empty_mi
    dh_pct = round((empty_mi / total_mi * 100), 1) if total_mi > 0 else 0
    st.info(f"**Trip:** {total_mi} miles total  •  {dh_pct}% deadhead")
    
    assets_df = fetch_assets()
    asset_options = ["None"] + assets_df["name"].tolist() if not assets_df.empty else ["None"]
    sel_asset = st.selectbox("Assign Asset (optional)", asset_options)
    asset_id = None
    loaded_rate = 0.0
    empty_rate = 0.0
    if sel_asset != "None":
        asset_row = assets_df[assets_df["name"] == sel_asset].iloc[0]
        asset_id = int(asset_row["id"])
        loaded_rate = float(asset_row["loaded_rate_per_mile"])
        empty_rate = float(asset_row["empty_rate_per_mile"])
        st.caption(f"Loaded: ${loaded_rate:.2f}/mi  ·  Empty: ${empty_rate:.2f}/mi")
        est_driver_pay = (loaded_mi * loaded_rate) + (empty_mi * empty_rate)
        st.metric("Est. Driver Pay (this load)", f"${est_driver_pay:.2f}")
    
    notes = st.text_area("Notes")
    
    if st.button("Log Load with Deadhead"):
        conn = get_conn()
        c = conn.cursor()
        bol = f"LP-{datetime.now().strftime('%Y%m%d%H%M')}"
        c.execute("""INSERT INTO loads (lead_id, shipper, pickup_date, commodity, weight_tons, rate_per_ton, total_revenue, loaded_miles, deadhead_miles, miles, origin, destination, bol_number, notes, status, asset_id)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (lead_id, sel_lead, str(l_date), comm, wgt, rate, round(wgt*rate,2), loaded_mi, empty_mi, loaded_mi + empty_mi, "Spruce Pine, NC", "Central Georgia (Kohler area)", bol, notes, "Logged", asset_id))
        conn.commit()
        conn.close()
        st.success(f"Load logged. BOL: {bol}")
        st.rerun()

    st.divider()
    st.markdown("#### Driver Load Acceptance & Status")
    st.caption("When the driver accepts a load, the customer sees live billing instantly.")
    conn = get_conn()
    accept_loads = pd.read_sql(
        "SELECT id, bol_number, shipper, commodity, total_revenue, status, accepted_at FROM loads ORDER BY id DESC",
        conn,
    )
    conn.close()
    if accept_loads.empty:
        st.caption("No loads yet — log one above.")
    else:
        LOAD_FLOW = ["Logged", "Accepted", "In Transit", "Delivered", "Invoiced", "Paid"]
        acc_map = {f"{r['bol_number']} — {r['shipper']} ({r['status']})": r.to_dict() for _, r in accept_loads.iterrows()}
        acc_sel = st.selectbox("Load", list(acc_map.keys()), key="accept_load_sel")
        acc_load = acc_map[acc_sel]
        cur_status = acc_load.get("status") or "Logged"
        cA, cB = st.columns([2, 1])
        with cA:
            new_load_status = st.selectbox(
                "Status",
                LOAD_FLOW,
                index=LOAD_FLOW.index(cur_status) if cur_status in LOAD_FLOW else 0,
                key="accept_load_status",
            )
        with cB:
            st.metric("Live Revenue", f"${float(acc_load.get('total_revenue') or 0):,.0f}")
        if acc_load.get("accepted_at"):
            st.success(f"Accepted {acc_load['accepted_at']} — billing is live for the customer.")
        if st.button("Update Load Status", key="accept_load_btn", use_container_width=True):
            conn = get_conn()
            if new_load_status in ("Accepted", "In Transit", "Delivered", "Invoiced", "Paid") and not acc_load.get("accepted_at"):
                conn.execute(
                    "UPDATE loads SET status=?, accepted_at=datetime('now') WHERE id=?",
                    (new_load_status, int(acc_load["id"])),
                )
                from lp_helpers.billing import queue_invoice
                queue_invoice(int(acc_load["id"]))
            else:
                conn.execute("UPDATE loads SET status=? WHERE id=?", (new_load_status, int(acc_load["id"])))
            # keep any linked PO load rows in sync
            conn.execute(
                "UPDATE po_loads SET status=? WHERE load_id=?",
                (new_load_status if new_load_status in ("Scheduled", "In Transit", "Delivered", "Cancelled") else "In Transit", int(acc_load["id"])),
            )
            conn.commit()
            conn.close()
            st.success(f"{acc_load['bol_number']} → {new_load_status}. Customer billing updated in real time.")
            st.rerun()

    st.divider()
    if st.button("📲 Open Driver App", key="open_driver_app", use_container_width=True,
                 on_click=lambda: st.session_state.update(screen="Driver")):
        pass

# ========== RATE CALCULATOR ==========
if screen == "Rate Calculator":
    st.markdown('<div class="lf-page-title">Rate Calculator</div>', unsafe_allow_html=True)
    st.caption("Quote fast — know your margin before you commit")
    st.subheader("Rate Calculator (with Deadhead)")
    w = st.slider("Tons", 10.0, 24.0, 22.0)
    r = st.number_input("Rate/Ton", 30.0, 120.0, 55.0)
    lm = st.number_input("Loaded Miles", 200, 350, 280)
    em = st.number_input("Empty Miles", 0, 350, 280)
    
    rev = w * r
    tot_m = lm + em
    st.metric("Est. Revenue", f"${rev:,.2f}")
    st.caption(f"Revenue per total mile: ${rev/tot_m:.2f}" if tot_m > 0 else "")
    
    assets_df = fetch_assets()
    if not assets_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            asset_sel = st.selectbox("Asset profile", assets_df["name"].tolist())
        arow = assets_df[assets_df["name"] == asset_sel].iloc[0]
        lr = float(arow["loaded_rate_per_mile"])
        er = float(arow["empty_rate_per_mile"])
        driver_pay = (lm * lr) + (em * er)
        c2.metric("Est. Driver Pay", f"${driver_pay:.2f}")
        net_margin = rev - driver_pay
        st.metric("Est. Net Margin (revenue - driver pay)", f"${net_margin:.2f}")

# ========== BILLING & DRIVER PAY ==========
if screen == "Billing & Pay":
    st.markdown('<div class="lf-page-title">Billing &amp; Driver Pay</div>', unsafe_allow_html=True)
    st.caption("Pay for the miles they drove — every time")
    st.subheader("Billing & Driver Pay")
    conn = get_conn()
    
    with st.expander("Asset / Pay Profile Manager", expanded=False):
        st.caption("Define trucks, trailers, or combos with per-mile rates.")
        with st.form("add_asset"):
            a1, a2 = st.columns(2)
            asset_type = a1.selectbox("Type", ["Truck+Trailer", "Truck", "Trailer"])
            asset_name = a2.text_input("Name")
            asset_desc = st.text_input("Description")
            c1, c2 = st.columns(2)
            loaded_rate = c1.number_input("Loaded $/mile", 0.0, 10.0, 1.75, 0.05)
            empty_rate = c2.number_input("Empty $/mile", 0.0, 10.0, 0.85, 0.05)
            if st.form_submit_button("Add Asset"):
                if asset_name.strip():
                    conn.execute(
                        "INSERT INTO assets (asset_type, name, description, loaded_rate_per_mile, empty_rate_per_mile) VALUES (?,?,?,?,?)",
                        (asset_type, asset_name.strip(), asset_desc, loaded_rate, empty_rate)
                    )
                    conn.commit()
                    st.success("Asset added.")
                    st.rerun()
        
        assets = fetch_assets()
        if not assets.empty:
            st.dataframe(assets, use_container_width=True, hide_index=True)
        else:
            st.caption("No assets yet.")
    
    st.divider()
    
    st.markdown("#### Route Editor")
    loads_df = pd.read_sql("SELECT id, bol_number, shipper, commodity, loaded_miles, deadhead_miles, pickup_date FROM loads ORDER BY pickup_date DESC", conn)
    if loads_df.empty:
        st.warning("Need loads to setup routes.")
    else:
        route_load_map = {f"{r['bol_number']} — {r['shipper']} ({r.get('pickup_date','')})": int(r['id']) for _, r in loads_df.iterrows()}
        sel_route_load = st.selectbox("Select load for route", list(route_load_map.keys()), key="rte_load_sel")
        r_load_id = route_load_map[sel_route_load]
        rload_row = loads_df[loads_df['id'] == r_load_id].iloc[0]
        rt_planned_loaded = float(rload_row.get('loaded_miles') or 0)
        rt_planned_empty = float(rload_row.get('deadhead_miles') or 0)
        
        rt_existing = fetch_routes(load_id=r_load_id)
        rt_default_waypoints = f"Spruce Pine, NC → {rload_row.get('shipper','')} → {rload_row.get('destination','Kohler area, GA')}"
        
        with st.form("route_form"):
            wp = st.text_input("Waypoints (comma separated)", value=rt_default_waypoints)
            google_miles = st.number_input("Google/ Commercial Miles", 0.0, 2000.0, float(rt_planned_loaded + rt_planned_empty), 1.0)
            rt_actual_loaded = st.number_input("Actual Loaded Miles", 0.0, 1000.0, rt_planned_loaded, 1.0)
            rt_actual_empty = st.number_input("Actual Empty Miles", 0.0, 1000.0, rt_planned_empty, 1.0)
            rt_notes = st.text_input("Route notes")
            save_routed = st.form_submit_button("Save Route", use_container_width=True)
        
        if save_routed:
            save_route(r_load_id, wp, rt_planned_loaded, rt_planned_empty, google_miles, 'planned', rt_notes)
            st.success("Route saved.")
            st.rerun()
        
        if not rt_existing.empty:
            st.markdown("##### Saved Routes")
            st.dataframe(rt_existing[[ 'id', 'waypoints', 'planned_loaded_miles', 'planned_empty_miles', 'google_miles', 'actual_loaded_miles', 'actual_empty_miles', 'source']], use_container_width=True, hide_index=True)
            
            upd_route_id = st.selectbox("Update actuals for route", ["—"] + [f"#{r['id']}" for _, r in rt_existing.iterrows()])
            if upd_route_id != "—":
                rid = int(upd_route_id.replace("#", ""))
                rrow = rt_existing[rt_existing['id'] == rid].iloc[0]
                au1, au2 = st.columns(2)
                with au1:
                    u_actual_loaded = st.number_input("Actual Loaded Miles", 0.0, value=float(rrow.get('actual_loaded_miles') or rrow['planned_loaded_miles']), key="u_al")
                with au2:
                    u_actual_empty = st.number_input("Actual Empty Miles", 0.0, value=float(rrow.get('actual_empty_miles') or rrow['planned_empty_miles']), key="u_ae")
                if st.button("Update Route Actuals", key="upd_rte_act"):
                    update_route_actuals(rid, u_actual_loaded, u_actual_empty)
                    st.success("Actual miles updated.")
                    st.rerun()

        st.markdown("##### 📡 ELD / In-Cab Hardware")
        st.caption("Pull the miles the truck actually drove straight from the ELD device. Pay follows actual miles.")
        e1, e2 = st.columns(2)
        eld_loaded = e1.number_input("ELD loaded miles", 0.0, 2000.0, float(rt_planned_loaded), 1.0, key="eld_loaded")
        eld_empty = e2.number_input("ELD empty miles", 0.0, 2000.0, float(rt_planned_empty), 1.0, key="eld_empty")
        if st.button("Push actuals from ELD device", key="eld_push", use_container_width=True):
            res = ingest_eld_miles(r_load_id, eld_loaded, eld_empty)
            verb = "created new route from" if res["route_created"] else "updated route with"
            st.success(f"ELD {verb} {res['actual_total_miles']:.0f} actual miles. Driver pay will use these miles.")
            st.rerun()
    
    st.divider()
    
    st.markdown("#### Variance Report")
    routes_all = fetch_routes()
    if routes_all.empty:
        st.caption("No routes yet.")
    else:
        report_rows = []
        for _, rr in routes_all.iterrows():
            basis = rr['google_miles'] if rr.get('google_miles') and rr['google_miles'] > 0 else (rr['planned_loaded_miles'] + rr['planned_empty_miles'])
            actual_l = rr.get('actual_loaded_miles') or 0
            actual_e = rr.get('actual_empty_miles') or 0
            actual_total = actual_l + actual_e
            var = variance_pct(basis, actual_total)
            report_rows.append({
                'Route ID': rr['id'],
                'Load ID': rr['load_id'],
                'Basis Miles': round(basis, 1),
                'Actual Total': round(actual_total, 1),
                'Variance %': var,
                'Flagged': 'Yes' if abs(var) > 10.0 else 'No',
                'Source': rr.get('source', 'planned'),
            })
        var_df = pd.DataFrame(report_rows)
        st.dataframe(var_df, use_container_width=True, hide_index=True)
    
    st.divider()
    
    st.markdown("#### Create Settlement")
    loads_df = pd.read_sql("SELECT id, bol_number, shipper, commodity, loaded_miles, deadhead_miles, pickup_date, route_id FROM loads ORDER BY pickup_date DESC", conn)
    asset_options = fetch_assets()
    if loads_df.empty or asset_options.empty:
        st.warning("Need loads and assets to create a settlement.")
    else:
        load_map = {f"{r['bol_number']} — {r['shipper']} ({r['commodity']})": int(r['id']) for _, r in loads_df.iterrows()}
        asset_map = {r['name']: int(r['id']) for _, r in asset_options.iterrows()}
        
        c1, c2 = st.columns(2)
        with c1:
            sel_load = st.selectbox("Load", list(load_map.keys()))
            load_id = load_map[sel_load]
            load_row = loads_df[loads_df['id'] == load_id].iloc[0]
            driver_name = st.text_input("Driver Name", value="Phillip / Lawson")
        with c2:
            sel_asset = st.selectbox("Asset", list(asset_map.keys()))
            asset_id = asset_map[sel_asset]
        
        # Check for route actuals
        routes_df = fetch_routes(load_id=load_id)
        use_route_actuals = False
        if not routes_df.empty:
            use_route_actuals = st.checkbox("Use actual route miles (if logged)", value=False)
            if use_route_actuals:
                rrow = routes_df.iloc[0]
                rt_actual_loaded = float(rrow.get('actual_loaded_miles') or rrow['planned_loaded_miles'])
                rt_actual_empty = float(rrow.get('actual_empty_miles') or rrow['planned_empty_miles'])
                rt_google = rrow.get('google_miles')
                variance_result = route_variance_analysis(rt_actual_loaded + rt_actual_empty, rt_actual_loaded + rt_actual_empty, rt_google, tolerance_pct=10.0)
                st.caption(f"Using route actuals: {rt_actual_loaded:.0f} loaded · {rt_actual_empty:.0f} empty · Google basis {variance_result['basis_miles']:.0f} mi")
            else:
                rt_actual_loaded = None
                rt_actual_empty = None
        else:
            rt_actual_loaded = None
            rt_actual_empty = None
        
        arow = asset_options[asset_options['id'] == asset_id].iloc[0]
        default_loaded_rate = float(arow['loaded_rate_per_mile'])
        default_empty_rate = float(arow['empty_rate_per_mile'])
        
        planned_loaded = float(load_row['loaded_miles'] or 0)
        planned_empty = float(load_row['deadhead_miles'] or 0)
        
        st.caption(f"Planned from load: {planned_loaded:.0f} loaded · {planned_empty:.0f} empty · {planned_loaded + planned_empty:.0f} total")
        
        m1, m2 = st.columns(2)
        with m1:
            if use_route_actuals and rt_actual_loaded is not None:
                actual_loaded = st.number_input("Actual Loaded Miles", 0.0, 600.0, rt_actual_loaded, 1.0)
            else:
                actual_loaded = st.number_input("Actual Loaded Miles", 0, 600, int(planned_loaded), 1)
        with m2:
            if use_route_actuals and rt_actual_empty is not None:
                actual_empty = st.number_input("Actual Empty Miles", 0.0, 600.0, rt_actual_empty, 1.0)
            else:
                actual_empty = st.number_input("Actual Empty Miles", 0, 600, int(planned_empty), 1)
        
        r1, r2 = st.columns(2)
        with r1:
            loaded_rate_in = st.number_input("Loaded $/mile", 0.0, 10.0, default_loaded_rate, 0.05)
        with r2:
            empty_rate_in = st.number_input("Empty $/mile", 0.0, 10.0, default_empty_rate, 0.05)
        
        bonuses = st.number_input("Bonuses", 0.0, 5000.0, 0.0, 10.0)
        accessorials = st.number_input("Accessorials", 0.0, 5000.0, 0.0, 10.0)
        deductions = st.number_input("Deductions", 0.0, 5000.0, 0.0, 10.0)
        
        # L&P policy: driver is ALWAYS paid for actual miles driven.
        # Google/planned is reference only; large deviation is flagged for review.
        rt_google_miles = None
        if not routes_df.empty:
            rt_google_miles = float(routes_df.iloc[0]['google_miles']) if routes_df.iloc[0].get('google_miles') else None
        decision = pay_decision(
            actual_loaded, actual_empty, loaded_rate_in, empty_rate_in,
            google_miles=rt_google_miles,
            planned_loaded_miles=planned_loaded, planned_empty_miles=planned_empty,
            bonuses=bonuses, accessorials=accessorials, deductions=deductions,
            tolerance_pct=10.0,
        )
        var = decision["variance_pct"]
        flag = decision["flagged"]
        base_pay = decision["pay"]["base_pay"]
        total_pay = decision["total_pay"]
        
        st.markdown(f"**Base pay (actual miles):** ${base_pay:,.2f}  |  **Bonuses:** ${bonuses:.2f}  |  **Accessorials:** ${accessorials:.2f}  |  **Deductions:** ${deductions:.2f}")
        st.info(f"💡 **Pay decision:** {decision['message']}")
        if flag:
            st.error(f"⚠️ Route variance: {var:+.1f}% — flagged for dispatcher review (threshold ±10%). Pay is unchanged — driver is paid for miles driven.")
        else:
            st.success(f"Route variance: {var:+.1f}% — within tolerance.")
            st.metric("Total Driver Pay", f"${total_pay:,.2f}", help="Always calculated on actual miles driven.")
            
            quickpay = st.checkbox("⚡ QuickPay (instant driver pay)", value=False,
                                   help="Mark this settlement for instant funding.")
            
            if st.button("Save Settlement", type="primary", use_container_width=True):
                cur = conn.execute(
                    """
                    INSERT INTO settlements (load_id, asset_id, driver_name, planned_loaded_miles, actual_loaded_miles, planned_empty_miles, actual_empty_miles, loaded_rate, empty_rate, bonuses, deductions, accessorials, total_pay, variance_pct, quickpay, status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (load_id, asset_id, driver_name, planned_loaded, actual_loaded, planned_empty, actual_empty, loaded_rate_in, empty_rate_in, bonuses, deductions, accessorials, total_pay, var, 1 if quickpay else 0, 'Draft')
                )
                if use_route_actuals and not routes_df.empty:
                    conn.execute(
                        "UPDATE routes SET updated_at = datetime('now') WHERE id = ?",
                        (int(routes_df.iloc[0]['id']),)
                    )
                conn.commit()
                st.success("Settlement saved." + (" ⚡ QuickPay queued." if quickpay else ""))
                st.rerun()
    
    st.divider()
    
    st.markdown("#### Settlement History")
    setts = fetch_settlements()
    if setts.empty:
        st.caption("No settlements yet.")
    else:
        st.dataframe(setts, use_container_width=True, hide_index=True)
        
        selected_label = st.selectbox("Preview settlement", ["— select —"] + [f"#{r['id']} — {r['bol_number']} — {r.get('driver_name', '-')}" for _, r in setts.iterrows()])
        if selected_label != "— select —":
            sid = int(selected_label.split(" — ")[0].replace("#", ""))
            srow = setts[setts['id'] == sid].iloc[0]
            conn_load = get_conn()
            loads_all = pd.read_sql("SELECT * FROM loads ORDER BY pickup_date DESC", conn_load)
            conn_load.close()
            lrow = loads_all[loads_all['id'] == srow['load_id']].iloc[0] if not loads_all.empty else {}
            
            sdict = {
                'driver_name': srow['driver_name'],
                'planned_loaded_miles': srow['planned_loaded_miles'],
                'actual_loaded_miles': srow['actual_loaded_miles'],
                'planned_empty_miles': srow['planned_empty_miles'],
                'actual_empty_miles': srow['actual_empty_miles'],
                'loaded_rate': srow['loaded_rate'],
                'empty_rate': srow['empty_rate'],
                'bonuses': srow['bonuses'],
                'deductions': srow['deductions'],
                'accessorials': srow['accessorials'],
                'total_pay': srow['total_pay'],
                'variance_pct': srow['variance_pct'],
            }
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Download Settlement PDF", use_container_width=True):
                    pdf_bytes = settlement_pdf(sdict, lrow, srow['asset_name'])
                    st.download_button("Save Settlement", pdf_bytes, f"settlement_{srow['bol_number']}_{srow['id']}.pdf", "application/pdf", use_container_width=True)
            with c2:
                if st.button("Download Invoice Preview", use_container_width=True):
                    inv_bytes = invoice_preview_pdf(lrow)
                st.download_button("Save Invoice", inv_bytes, f"invoice_{srow['bol_number']}_{srow['id']}.pdf", "application/pdf", use_container_width=True)
    
    st.divider()
    st.markdown("#### Customer Invoices")
    st.caption("Auto-created the moment a load is accepted. Send or QuickPay in one tap.")
    inv_conn = get_conn()
    invoices = pd.read_sql(
        "SELECT i.id, i.load_id, i.status, i.created_at, l.bol_number, l.shipper, l.total_revenue "
        "FROM invoices i LEFT JOIN loads l ON i.load_id = l.id ORDER BY i.created_at DESC",
        inv_conn,
    )
    inv_conn.close()
    if invoices.empty:
        st.info("No invoices yet — accept a load to auto-generate one.")
    else:
        for _, inv in invoices.iterrows():
            rev = inv.get("total_revenue") or 0
            pill = "green" if inv["status"] == "Sent" else "amber"
            st.markdown(
                f'<div class="lf-card">'
                f'<div class="lf-row"><b>{inv["bol_number"]}</b>'
                f'<span class="lf-pill {pill}"><span class="lf-dot"></span>{inv["status"]}</span></div>'
                f'<div class="lf-muted">{inv["shipper"]} &middot; ${float(rev):,.0f}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                inv_load = fetch_load(int(inv["load_id"])) if inv["load_id"] else None
                if inv_load is not None:
                    st.download_button(
                        "Download", generate_invoice_pdf(inv_load),
                        file_name=f"invoice_{inv['bol_number']}.pdf", mime="application/pdf",
                        key=f"inv_dl_{inv['id']}", use_container_width=True,
                    )
            with c2:
                if st.button("Mark Sent", key=f"inv_send_{inv['id']}", use_container_width=True):
                    mark_invoice_sent(int(inv["id"]))
                    st.rerun()
            with c3:
                if st.button("⚡ QuickPay", key=f"inv_qp_{inv['id']}", use_container_width=True, type="secondary"):
                    mark_invoice_sent(int(inv["id"]))
                    st.toast("QuickPay initiated — funds arriving fast.")
                    st.rerun()
    
    conn.close()

# ========== BOL ==========
if screen == "BOL":
    st.markdown('<div class="lf-page-title">Generate BOL</div>', unsafe_allow_html=True)
    st.caption("Bill of lading — PDF, ready to roll")
    st.subheader("Generate BOL")
    st.caption("Create a printable PDF Bill of Lading. Pick a logged load or enter details manually.")

    conn = get_conn()
    bol_loads = pd.read_sql(
        "SELECT id, bol_number, shipper, commodity, weight_tons, rate_per_ton, origin, destination, pickup_date, notes FROM loads ORDER BY pickup_date DESC, id DESC",
        conn,
    )
    conn.close()

    load_choice = "— Manual entry —"
    if not bol_loads.empty:
        bol_load_map = {f"{r['bol_number']} — {r['shipper']} ({r['commodity']})": r.to_dict() for _, r in bol_loads.iterrows()}
        load_choice = st.selectbox("Source", ["— Manual entry —"] + list(bol_load_map.keys()))

    if load_choice != "— Manual entry —":
        src = bol_load_map[load_choice]
        bol_no = str(src.get("bol_number") or f"LP-{datetime.now().strftime('%Y%m%d%H%M')}")
        ship = st.text_input("Shipper", value=str(src.get("shipper") or ""))
        com = st.text_input("Commodity", value=str(src.get("commodity") or ""))
        wt = st.number_input("Weight (tons)", value=float(src.get("weight_tons") or 22.0))
        rt = st.number_input("Rate per Ton", value=float(src.get("rate_per_ton") or 55.0))
        origin = str(src.get("origin") or "Spruce Pine, NC")
        destination = str(src.get("destination") or "Central Georgia (Kohler area)")
        pickup = src.get("pickup_date")
        bol_notes = str(src.get("notes") or "")
    else:
        bol_no = f"LP-{datetime.now().strftime('%Y%m%d%H%M')}"
        ship = st.text_input("Shipper")
        com = st.text_input("Commodity")
        wt = st.number_input("Weight (tons)", value=22.0)
        rt = st.number_input("Rate per Ton", value=55.0)
        origin = "Spruce Pine, NC"
        destination = "Central Georgia (Kohler area)"
        pickup = None
        bol_notes = ""

    st.metric("Total Revenue", f"${wt * rt:,.2f}")

    if st.button("Generate PDF BOL", type="primary"):
        pdf_bytes = bol_pdf(bol_no, ship, com, wt, rt, origin, destination, pickup, bol_notes)
        st.download_button(
            "Download BOL (PDF)",
            pdf_bytes,
            file_name=f"BOL_{str(bol_no).replace('/', '-')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        st.success(f"BOL {bol_no} generated.")

# ========== CUSTOMER PORTAL ==========
if screen == "Portal":
    st.markdown('<div class="lf-page-title">Customer Portal</div>', unsafe_allow_html=True)
    st.caption("Live tracking & billing your customers see")
    st.subheader("Customer Portal")
    st.caption("Self-service tracking, billing, and dispatch requests.")
    
    if 'new_po_id' not in st.session_state:
        st.session_state.new_po_id = None
    customers_df = fetch_customers()
    if customers_df.empty:
        st.warning("No customers configured.")
    else:
        cust_map = {f"{r['name']} ({r.get('contact_name','')})": int(r['id']) for _, r in customers_df.iterrows()}
        sel_cust = st.selectbox("View as Customer", list(cust_map.keys()), key="portal_customer")
        cust_id = cust_map[sel_cust]
        cust_row = customers_df[customers_df['id'] == cust_id].iloc[0]
        
        st.markdown(f"**Contact:** {cust_row.get('contact_name', '—')}  ·  **Phone:** {cust_row.get('phone', '—')}  ·  **Email:** {cust_row.get('email', '—')}")
        
        summary = get_customer_po_summary(cust_id)
        conn = get_conn()
        live_billing = pd.read_sql(
            """
            SELECT COALESCE(SUM(l.total_revenue), 0) AS billed, COUNT(*) AS n
            FROM po_loads pl
            JOIN purchase_orders po ON pl.po_id = po.id
            JOIN loads l ON pl.load_id = l.id
            WHERE po.customer_id = ? AND l.accepted_at IS NOT NULL
            """,
            conn, params=(cust_id,),
        )
        conn.close()
        billed_amt = float(live_billing.iloc[0]['billed'] or 0)
        billed_n = int(live_billing.iloc[0]['n'] or 0)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Open POs", summary['open_pos'])
        c2.metric("Scheduled Loads", summary['scheduled_loads'])
        c3.metric("Est. Revenue", f"${summary['total_est_revenue']:,.0f}")
        c4.metric("Live Billing", f"${billed_amt:,.0f}", help=f"{billed_n} accepted load(s) billing in real time")
    
    st.divider()
    
    tab_p1, tab_p2, tab_p3 = st.tabs(["My Loads & Tracking", "My Purchase Orders", "New Dispatch Request"])
    
    with tab_p1:
        st.markdown("#### Load Tracking Dashboard")
        if customers_df.empty:
            st.info("No customers.")
        else:
            po_df = fetch_purchase_orders(customer_id=cust_id)
            if po_df.empty:
                st.info("No purchase orders yet.")
            else:
                po_ids = po_df['id'].tolist()
                conn = get_conn()
                placeholders = ",".join("?" * len(po_ids))
                poloads = pd.read_sql(f"""
                    SELECT pl.*, l.id as real_load_id, l.bol_number, l.shipper, l.commodity, l.origin, l.destination, l.loaded_miles, l.deadhead_miles, l.weight_tons, l.rate_per_ton, l.total_revenue, l.status as load_status, l.accepted_at, l.pickup_date
                    FROM po_loads pl
                    LEFT JOIN loads l ON pl.load_id = l.id
                    WHERE pl.po_id IN ({placeholders})
                    ORDER BY pl.sequence, pl.id
                """, conn, params=po_ids)
                conn.close()
                
                if poloads.empty:
                    st.info("No loads linked to your POs yet.")
                else:
                    for _, plrow in poloads.iterrows():
                        live_status = plrow.get('load_status') or plrow.get('status') or 'Scheduled'
                        status_color = {"Scheduled": "blue", "Logged": "gray", "Accepted": "teal", "In Transit": "orange", "Delivered": "green", "Invoiced": "purple", "Paid": "green", "Cancelled": "red"}.get(live_status, "gray")
                        is_billing = pd.notna(plrow.get('accepted_at')) and bool(plrow.get('accepted_at'))
                        revenue = plrow.get('total_revenue', 0) if pd.notna(plrow.get('total_revenue', 0)) else 0
                        billing_line = (
                            f"<span style='color:#059669;font-weight:700;'>● BILLING LIVE</span> since {plrow.get('accepted_at')}"
                            if is_billing else
                            "<span style='color:#94a3b8;'>Billing starts when driver accepts</span>"
                        )
                        st.markdown(
                            f"<div style='padding:0.75rem;border-left:4px solid {status_color};background:#f8fafc;margin-bottom:0.5rem;border-radius:6px;'>"
                            f"<b>Seq {plrow.get('sequence', '—')}</b> · {plrow.get('bol_number', 'Unlinked')} · {plrow.get('commodity', '—')}<br>"
                            f"Status: <b>{live_status}</b> · "
                            f"Revenue: ${revenue:,.0f}<br>"
                            f"{plrow.get('origin', '')} → {plrow.get('destination', '')}<br>"
                            f"{billing_line}"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                        if is_billing and pd.notna(plrow.get('real_load_id')):
                            inv_load = {
                                'shipper': plrow.get('shipper'),
                                'bol_number': plrow.get('bol_number'),
                                'commodity': plrow.get('commodity'),
                                'weight_tons': plrow.get('weight_tons') or 0,
                                'loaded_miles': plrow.get('loaded_miles') or 0,
                                'deadhead_miles': plrow.get('deadhead_miles') or 0,
                                'rate_per_ton': plrow.get('rate_per_ton') or 0,
                                'total_revenue': revenue,
                            }
                            st.download_button(
                                "Download live invoice (PDF)",
                                invoice_preview_pdf(inv_load),
                                file_name=f"invoice_{plrow.get('bol_number','load')}.pdf",
                                mime="application/pdf",
                                key=f"cust_inv_{plrow.get('id')}",
                            )
    
    with tab_p2:
        st.markdown("#### My Purchase Orders")
        if customers_df.empty:
            st.info("No customers.")
        else:
            po_df = fetch_purchase_orders(customer_id=cust_id)
            if po_df.empty:
                st.info("No purchase orders yet.")
            else:
                for _, porow in po_df.iterrows():
                    with st.expander(f"PO {porow['po_number']} — {porow['status']} — Est. ${porow.get('total_estimated_revenue', 0) or 0:,.0f}"):
                        st.write(f"**Created:** {porow.get('created_at', '')}")
                        st.write(f"**Notes:** {porow.get('notes', '') or '—'}")
                        st.write(f"**Status:** {porow['status']}")
                        pol_df = fetch_po_loads(po_id=int(porow['id']))
                        if pol_df.empty:
                            st.caption("No loads scheduled yet.")
                        else:
                            st.dataframe(pol_df[['sequence', 'scheduled_pickup_date', 'scheduled_delivery_date', 'status', 'bol_number', 'commodity']], use_container_width=True, hide_index=True)
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            if porow['status'] == 'Open' and st.button(f"Mark Complete", key=f"po_comp_{porow['id']}"):
                                update_po_status(int(porow['id']), 'Complete')
                                st.success("PO marked complete.")
                                st.rerun()
                        with c2:
                            if porow['status'] == 'Open':
                                new_status = st.selectbox("Update status", ["Open", "In Progress", "Complete", "Cancelled"], index=0, key=f"po_st_{porow['id']}")
                                if new_status != porow['status'] and st.button("Update", key=f"po_upd_{porow['id']}"):
                                    update_po_status(int(porow['id']), new_status)
                                    st.success("Status updated.")
                                    st.rerun()
    
    with tab_p3:
        st.markdown("#### New Dispatch Request / PO")
        if customers_df.empty:
            st.info("No customers configured.")
        else:
            with st.form("new_po_form"):
                po_number = st.text_input("PO Number *", placeholder="PO-2026-001")
                notes = st.text_area("Notes / Special instructions")
                submitted_po = st.form_submit_button("Create Purchase Order", use_container_width=True)
            
            if submitted_po:
                if not po_number.strip():
                    st.error("PO number is required.")
                else:
                    po_id = create_purchase_order(cust_id, po_number.strip(), notes=notes)
                    st.success(f"Purchase Order created — PO #{po_number.strip()}")
                    st.session_state.new_po_id = po_id
                    st.rerun()
            
            if st.session_state.get('new_po_id'):
                st.divider()
                st.markdown(f"##### Add up to 16 loads to PO #{st.session_state['new_po_id']}")
                conn = get_conn()
                loads_all = pd.read_sql("SELECT id, bol_number, shipper, commodity FROM loads ORDER BY pickup_date DESC", conn)
                conn.close()
                if loads_all.empty:
                    st.info("No loads in system to link. Log a load first.")
                else:
                    load_opts = {f"{r['bol_number']} — {r['shipper']} ({r['commodity']})": int(r['id']) for _, r in loads_all.iterrows()}
                    sel_load = st.selectbox("Select load to add", list(load_opts.keys()), key="po_add_load")
                    load_id = load_opts[sel_load]
                    seq = st.number_input("Sequence", 1, 16, 1, 1)
                    pickup = st.date_input("Scheduled Pickup", value=date.today())
                    delivery = st.date_input("Scheduled Delivery", value=date.today() + timedelta(days=3))
                    load_notes = st.text_input("Load notes")
                    if st.button("Add Load to PO", use_container_width=True):
                        add_po_load(st.session_state['new_po_id'], load_id, sequence=seq, pickup_date=pickup, delivery_date=delivery, notes=load_notes)
                        st.success("Load added to PO.")
                        st.rerun()
                
                if st.button("Finish PO Setup", use_container_width=True):
                    po_id = int(st.session_state.pop('new_po_id'))
                    st.success(f"PO setup complete.")
                    st.rerun()

st.caption("L & P Freight v3.2 — Billing & Driver Pay + Customer Portal + Routing Editor")

# ========== NOTIFICATIONS ==========
if screen == "Notifications":
    st.markdown('<div class="lf-page-title">Notifications</div>', unsafe_allow_html=True)
    st.caption("Today’s alerts, grouped &amp; actionable")
    data = get_notifications()
    if data["unread"] == 0:
        empty_state("🔔", "You’re all caught up", "New leads, load accepts, and variance flags will appear here.")
    else:
        for grp in ("Today", "Yesterday", "Earlier"):
            items = data["groups"].get(grp, [])
            if not items:
                continue
            st.markdown(f'<div class="lf-section">{grp} · {len(items)}</div>', unsafe_allow_html=True)
            for n in items:
                meta = CATEGORY_META.get(n["category"], ("Alert", "gray"))
                st.markdown(
                    f'<div class="lf-card">'
                    f'<div class="lf-row"><b>{n["title"]}</b>'
                    f'<span class="lf-pill {meta[1]}"><span class="lf-dot"></span>{meta[0]}</span></div>'
                    f'<div class="lf-muted">{n["detail"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                b1, b2 = st.columns(2)
                with b1:
                    st.button(
                        "View", key=f"nv_{n['key']}", use_container_width=True,
                        on_click=lambda s=n["screen"]: st.session_state.update(screen=s),
                    )
                with b2:
                    st.button(
                        "Dismiss", key=f"nd_{n['key']}", use_container_width=True, type="secondary",
                        on_click=lambda k=n["key"]: dismiss_notification(k),
                    )

# ========== DRIVER APP ==========
if screen == "Driver":
    st.markdown('<div class="lf-page-title">Driver App</div>', unsafe_allow_html=True)
    st.caption("Your loads, hours &amp; pay — in your pocket")

    hos = get_driver_hos()
    h1, h2, h3 = st.columns(3)
    h1.metric("Drive left", f"{hos['drive_remaining_hours']:.1f} h")
    h2.metric("On-duty left", f"{hos['on_duty_remaining_hours']:.1f} h")
    h3.metric("Cycle left", f"{hos['cycle_remaining_hours']:.0f} h")
    viol_cls = "red" if hos["violation"] else "green"
    st.markdown(
        f'<div class="lf-pill {viol_cls}"><span class="lf-dot"></span>'
        f'{"HOS violation" if hos["violation"] else "HOS compliant"} &middot; {hos["hours_today"]:.1f}h today</div>',
        unsafe_allow_html=True,
    )

    dv = get_driver_loads()
    st.markdown('<div class="lf-section">Pending — tap to accept</div>', unsafe_allow_html=True)
    if not dv["pending"]:
        st.info("No loads waiting for acceptance.")
    for l in dv["pending"]:
        st.markdown(
            f'<div class="lf-card">'
            f'<div class="lf-row"><b>{l["bol_number"]}</b><span class="lf-muted">{l["status"]}</span></div>'
            f'<div class="lf-muted">{l["shipper"]} &middot; {l["commodity"]}</div>'
            f'<div style="margin:0.35rem 0;font-weight:700;">{l["origin"]} <span style="color:var(--lf-orange)">→</span> {l["destination"]}</div>'
            f'<div class="lf-row"><span class="lf-muted">Pay on actual miles</span><b style="color:var(--lf-green)">${float(l["total_revenue"] or 0):,.0f}</b></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button(f"✅ Accept {l['bol_number']}", key=f"drv_acc_{l['id']}", use_container_width=True,
                     on_click=lambda lid=l["id"]: accept_load(lid)):
            pass

    st.markdown('<div class="lf-section">Active Loads</div>', unsafe_allow_html=True)
    if not dv["active"]:
        empty_state("🧑‍✈️", "No active loads", "Accept a pending load to get rolling.")
    for l in dv["active"]:
        photo = l.get("bol_photo_path")
        st.markdown(
            f'<div class="lf-card">'
            f'<div class="lf-row"><b>{l["bol_number"]}</b>'
            f'<span class="lf-pill orange"><span class="lf-dot"></span>{l["status"]}</span></div>'
            f'<div class="lf-muted">{l["shipper"]} &middot; {l["commodity"]}</div>'
            f'<div style="margin:0.35rem 0;font-weight:700;">{l["origin"]} <span style="color:var(--lf-orange)">→</span> {l["destination"]}</div>'
            f'<div class="lf-row"><span class="lf-muted">Revenue ${float(l["total_revenue"] or 0):,.0f}</span>'
            f'<b style="color:{"var(--lf-green)" if photo else "var(--lf-muted)"}">{"BOL ✔" if photo else "BOL pending"}</b></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        up = st.file_uploader(
            f"Upload signed BOL — {l['bol_number']}",
            type=["png", "jpg", "jpeg"],
            key=f"bol_up_{l['id']}",
        )
        if up is not None:
            save_bol_photo(int(l["id"]), up.name, up.getbuffer())
            st.success("BOL photo saved.")
            st.rerun()

# Persistent bottom navigation (mobile-first)
render_bottom_nav(SCREENS, st.session_state["screen"])