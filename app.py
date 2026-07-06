import streamlit as st
import sqlite3
from datetime import datetime, date, timedelta
import pandas as pd
from fpdf import FPDF

st.set_page_config(page_title="L & P Freight", layout="wide", page_icon="🚛")

# Custom CSS for top-tier contrast and polish
st.markdown("""
<style>
    .main .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    .stApp {background-color: #d4dce8 !important;}
    .stMetric {background-color: #e8edf4; border-radius: 12px; padding: 12px; border: 1px solid #b8c5d6;}
    .stMetric label {font-size: 0.85rem !important; color: #475569 !important;}
    .stMetric .metric-value {font-size: 1.6rem !important; font-weight: 700; color: #0f172a;}
    .dark .stMetric {background-color: #1e2937; border: 1px solid #334155;}
    .dark .stMetric .metric-value {color: #f1f5f9;}
    
    .kpi-card {
        background: #e8edf4;
        border-radius: 12px;
        padding: 16px;
        border: 1px solid #b8c5d6;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
    }
    .dark .kpi-card {
        background: #1e2937;
        border: 1px solid #334155;
    }
    
    .mission-banner {
        background: linear-gradient(90deg, #0ea5e9 0%, #0284c8 100%);
        color: white;
        padding: 14px 20px;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    
    .section-header {
        font-size: 1.25rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.75rem;
    }
    .dark .section-header {color: #f1f5f9;}
    
    .stDataFrame {border-radius: 10px; overflow: hidden;}
</style>
""", unsafe_allow_html=True)


def get_conn():
    conn = sqlite3.connect("l_and_p_freight.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_billing_schema():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            loaded_rate_per_mile REAL NOT NULL DEFAULT 0.0,
            empty_rate_per_mile REAL NOT NULL DEFAULT 0.0,
            status TEXT DEFAULT 'Active',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            load_id INTEGER NOT NULL,
            asset_id INTEGER,
            driver_name TEXT,
            planned_loaded_miles REAL NOT NULL,
            actual_loaded_miles REAL NOT NULL,
            planned_empty_miles REAL NOT NULL,
            actual_empty_miles REAL NOT NULL,
            loaded_rate REAL NOT NULL,
            empty_rate REAL NOT NULL,
            bonuses REAL DEFAULT 0.0,
            deductions REAL DEFAULT 0.0,
            accessorials REAL DEFAULT 0.0,
            total_pay REAL NOT NULL,
            variance_pct REAL,
            status TEXT DEFAULT 'Draft',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (load_id) REFERENCES loads(id),
            FOREIGN KEY (asset_id) REFERENCES assets(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            load_id INTEGER NOT NULL,
            waypoints TEXT NOT NULL,
            planned_loaded_miles REAL NOT NULL,
            planned_empty_miles REAL NOT NULL,
            google_miles REAL,
            actual_loaded_miles REAL,
            actual_empty_miles REAL,
            source TEXT DEFAULT 'planned',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (load_id) REFERENCES loads(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_name TEXT,
            phone TEXT,
            email TEXT,
            api_key TEXT UNIQUE,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            po_number TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'Open',
            total_estimated_revenue REAL DEFAULT 0.0,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS po_loads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id INTEGER NOT NULL,
            load_id INTEGER,
            sequence INTEGER DEFAULT 1,
            scheduled_pickup_date TEXT,
            scheduled_delivery_date TEXT,
            status TEXT DEFAULT 'Scheduled',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (po_id) REFERENCES purchase_orders(id),
            FOREIGN KEY (load_id) REFERENCES loads(id)
        )
    """)
    cols = [row[1] for row in c.execute("PRAGMA table_info(loads)").fetchall()]
    if 'asset_id' not in cols:
        c.execute("ALTER TABLE loads ADD COLUMN asset_id INTEGER")
    if 'route_id' not in cols:
        c.execute("ALTER TABLE loads ADD COLUMN route_id INTEGER")
    conn.commit()
    conn.close()

def seed_assets():
    conn = get_conn()
    c = conn.cursor()
    existing = c.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    if existing == 0:
        assets = [
            ("Truck+Trailer", "Tractor + 39ft End-Dump", "Primary unit", 1.75, 0.85),
            ("Truck+Trailer", "Backup Tractor + Trailer", "Secondary unit", 1.65, 0.80),
            ("Trailer", "39ft End-Dump Only", "Trailer only", 1.50, 0.75),
        ]
        for a in assets:
            c.execute("INSERT INTO assets (asset_type, name, description, loaded_rate_per_mile, empty_rate_per_mile) VALUES (?,?,?,?,?)", a)
        conn.commit()
    conn.close()


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
    total_miles = (load.get('loaded_miles', 0) or 0) + (load.get('empty_miles', 0) or 0)
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


st.title("🚛 L & P Freight — Mobile Command Center")
st.caption("Spruce Pine NC → Central Georgia (Kohler area)  |  v3.2 — Billing & Driver Pay")

init_billing_schema()
seed_assets()
init_customer_portal()
seed_demo_customers()

# SIDEBAR
with st.sidebar:
    st.header("L & P Freight")
    st.caption("v3.1 • Local Command Center")
    
    st.subheader("Trailer")
    st.write("**39 ft / 24-ton Frameless Lined End-Dump**")
    st.caption("Maximize loaded miles • Minimize deadhead")
    
    st.subheader("Hot Leads")
    st.write("Sibelco • Covia • K-T Feldspar • Trimac")

# MISSION BANNER
st.markdown("""
<div class="mission-banner">
<b>MISSION:</b> Build loaded miles from Spruce Pine, NC to Central Georgia (Kohler). 
Every empty mile is margin lost — prioritize backhauls and feldspar/quartz shippers on Hwy 19E & 226.
</div>
""", unsafe_allow_html=True)

# TABS
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Dashboard", "Leads & Follow-ups", "Log Load + Deadhead", "Rate Calculator", "Billing & Driver Pay", "Generate BOL", "Customer Portal"])

# ========== DASHBOARD ==========
with tab1:
    st.subheader("Dashboard — Today’s Snapshot")
    
    conn = sqlite3.connect("l_and_p_freight.db")
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
        total_loaded = loads_df['loaded_miles'].sum()
        total_empty = loads_df['empty_miles'].sum()
        deadhead_pct = round((total_empty / (total_loaded + total_empty) * 100), 1) if (total_loaded + total_empty) > 0 else 0
        
        st.info(f"**Deadhead Tracking:** {total_empty:,.0f} empty miles logged  •  {deadhead_pct}% of total miles")
    
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
        st.dataframe(due_leads[['name', 'phone', 'status', 'next_followup_date', 'followup_type']], use_container_width=True, hide_index=True)
    else:
        st.success("No follow-ups due today. Excellent discipline.")
    
    # Recent Activity
    if not loads_df.empty:
        st.subheader("Recent Loads")
        st.dataframe(loads_df[['load_date', 'commodity', 'weight_tons', 'loaded_miles', 'empty_miles', 'total_revenue']].tail(5), use_container_width=True)

# ========== LEADS & FOLLOW-UPS ==========
with tab2:
    st.subheader("Leads CRM + Automated Follow-up Sequences")
    
    conn = sqlite3.connect("l_and_p_freight.db")
    leads_df = pd.read_sql("SELECT * FROM leads", conn)
    conn.close()
    
    st.dataframe(leads_df[['name', 'phone', 'status', 'last_contact', 'next_followup_date', 'followup_type']], use_container_width=True, hide_index=True)
    
    st.divider()
    st.subheader("Update Lead & Set Next Follow-up")
    
    selected = st.selectbox("Select Lead", leads_df['name'].tolist())
    row = leads_df[leads_df['name'] == selected].iloc[0]
    
    new_status = st.selectbox("Status", ["New", "Contacted", "Quote Sent", "Booked", "On Hold", "Not Interested"], 
                              index=["New","Contacted","Quote Sent","Booked","On Hold","Not Interested"].index(row['status']))
    
    new_note = st.text_area("Call / Note Summary")
    
    colf1, colf2 = st.columns(2)
    with colf1:
        next_date = st.date_input("Next Follow-up Date", value=date.today() + timedelta(days=2))
    with colf2:
        f_type = st.selectbox("Follow-up Method", ["Phone Call", "Text", "Email", "Send Quote"])
    
    if st.button("Save Update & Schedule Follow-up"):
        conn = sqlite3.connect("l_and_p_freight.db")
        c = conn.cursor()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        combined = f"[{ts}] {new_note}\n{row['notes']}" if new_note else row['notes']
        c.execute("""UPDATE leads SET status=?, notes=?, last_contact=?, next_followup_date=?, followup_type=? WHERE id=?""",
                  (new_status, combined, ts, str(next_date), f_type, int(row['id'])))
        conn.commit()
        conn.close()
        st.success("Lead updated and follow-up scheduled.")
        st.rerun()

# ========== LOG LOAD + DEADHEAD ==========
with tab3:
    st.subheader("Log Load + Track Empty Return Miles")
    
    conn = sqlite3.connect("l_and_p_freight.db")
    leads = pd.read_sql("SELECT id, name FROM leads", conn)
    conn.close()
    
    lead_map = {r['name']: r['id'] for _, r in leads.iterrows()}
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
        conn = sqlite3.connect("l_and_p_freight.db")
        c = conn.cursor()
        bol = f"LP-{datetime.now().strftime('%Y%m%d%H%M')}"
        c.execute("""INSERT INTO loads (lead_id, load_date, commodity, weight_tons, rate_per_ton, total_revenue, loaded_miles, empty_miles, bol_number, notes, asset_id)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                  (lead_id, str(l_date), comm, wgt, rate, round(wgt*rate,2), loaded_mi, empty_mi, bol, notes, asset_id))
        conn.commit()
        conn.close()
        st.success(f"Load logged. BOL: {bol}")
        st.rerun()

# ========== RATE CALCULATOR ==========
with tab4:
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
with tab5:
    st.subheader("Billing & Driver Pay")
    conn = sqlite3.connect("l_and_p_freight.db")
    
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
    loads_df = pd.read_sql("SELECT id, bol_number, shipper, commodity, loaded_miles, empty_miles, pickup_date FROM loads ORDER BY pickup_date DESC", conn)
    if loads_df.empty:
        st.warning("Need loads to setup routes.")
    else:
        route_load_map = {f"{r['bol_number']} — {r['shipper']} ({r.get('pickup_date','')})": int(r['id']) for _, r in loads_df.iterrows()}
        sel_route_load = st.selectbox("Select load for route", list(route_load_map.keys()), key="rte_load_sel")
        r_load_id = route_load_map[sel_route_load]
        rload_row = loads_df[loads_df['id'] == r_load_id].iloc[0]
        rt_planned_loaded = float(rload_row.get('loaded_miles') or 0)
        rt_planned_empty = float(rload_row.get('empty_miles') or 0)
        
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
    loads_df = pd.read_sql("SELECT id, bol_number, shipper, commodity, loaded_miles, empty_miles, pickup_date, route_id FROM loads ORDER BY pickup_date DESC", conn)
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
        planned_empty = float(load_row['empty_miles'] or 0)
        
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
        
        # compute variance using route analysis if route exists
        actual_total = actual_loaded + actual_empty
        planned_total = planned_loaded + planned_empty
        rt_google_miles = None
        if not routes_df.empty:
            rt_google_miles = float(routes_df.iloc[0]['google_miles']) if routes_df.iloc[0].get('google_miles') else None
        var = variance_pct(planned_total, actual_total)
        if rt_google_miles:
            gvar = variance_pct(rt_google_miles, actual_total)
            if abs(gvar) > abs(var):
                var = gvar
        flag = abs(var) > 10.0
        base_pay = (actual_loaded * loaded_rate_in) + (actual_empty * empty_rate_in)
        total_pay = round(base_pay + bonuses + accessorials - deductions, 2)
        
        st.markdown(f"**Base pay:** ${base_pay:.2f}  |  **Bonuses:** ${bonuses:.2f}  |  **Accessorials:** ${accessorials:.2f}  |  **Deductions:** ${deductions:.2f}")
        if flag:
            st.error(f"⚠️ Route variance: {var:.1f}% — flagged for review (threshold ±10%)")
        else:
            st.success(f"Route variance: {var:.1f}% — within tolerance")
        st.metric("Total Driver Pay", f"${total_pay:.2f}")
        
        if st.button("Save Settlement", type="primary", use_container_width=True):
            conn.execute(
                """
                INSERT INTO settlements (load_id, asset_id, driver_name, planned_loaded_miles, actual_loaded_miles, planned_empty_miles, actual_empty_miles, loaded_rate, empty_rate, bonuses, deductions, accessorials, total_pay, variance_pct, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (load_id, asset_id, driver_name, planned_loaded, actual_loaded, planned_empty, actual_empty, loaded_rate_in, empty_rate_in, bonuses, deductions, accessorials, total_pay, var, 'Draft')
            )
            if use_route_actuals and not routes_df.empty:
                conn.execute(
                    "UPDATE routes SET updated_at = datetime('now') WHERE id = ?",
                    (int(routes_df.iloc[0]['id']),)
                )
            conn.commit()
            st.success("Settlement saved.")
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
            conn_load = sqlite3.connect("l_and_p_freight.db")
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
    
    conn.close()

# ========== BOL ==========
with tab6:
    st.subheader("Generate BOL")
    ship = st.text_input("Shipper")
    com = st.text_input("Commodity")
    wt = st.number_input("Weight (tons)", value=22.0)
    rt = st.number_input("Rate per Ton", value=55.0)
    
    if st.button("Generate BOL"):
        bol_text = f"""L & P FREIGHT — BILL OF LADING
Date: {datetime.now().strftime('%Y-%m-%d')}
BOL #: LP-{datetime.now().strftime('%Y%m%d%H%M')}
SHIPPER: {ship}
COMMODITY: {com}
WEIGHT: {wt} tons
RATE: ${rt:.2f}/ton
TOTAL: ${wt*rt:,.2f}
ORIGIN: Spruce Pine, NC
DESTINATION: Central Georgia (Kohler)
TRAILER: 39 ft Frameless End-Dump"""
        st.code(bol_text)
        st.download_button("Download BOL", bol_text, file_name="BOL.txt")

# ========== CUSTOMER PORTAL ==========
with tab7:
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
        c1, c2, c3 = st.columns(3)
        c1.metric("Open POs", summary['open_pos'])
        c2.metric("Scheduled Loads", summary['scheduled_loads'])
        c3.metric("Est. Revenue", f"${summary['total_est_revenue']:,.0f}")
    
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
                    SELECT pl.*, l.bol_number, l.shipper, l.commodity, l.origin, l.destination, l.loaded_miles, l.empty_miles, l.total_revenue, l.status as load_status
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
                        status_color = {"Scheduled": "blue", "In Transit": "orange", "Delivered": "green", "Cancelled": "red"}.get(plrow.get('status', 'Scheduled'), "gray")
                        st.markdown(
                            f"<div style='padding:0.75rem;border-left:4px solid {status_color};background:#f8fafc;margin-bottom:0.5rem;border-radius:6px;'>"
                            f"<b>Seq {plrow.get('sequence', '—')}</b> · {plrow.get('bol_number', 'Unlinked')} · {plrow.get('commodity', '—')}<br>"
                            f"Status: <b>{plrow.get('status', 'Scheduled')}</b> · "
                            f"Revenue: ${plrow.get('total_revenue', 0) if pd.notna(plrow.get('total_revenue', 0)) else 0:,.0f}<br>"
                            f"{plrow.get('origin', '')} → {plrow.get('destination', '')}"
                            f"</div>",
                            unsafe_allow_html=True
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