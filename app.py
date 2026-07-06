import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

st.set_page_config(page_title="Lawson Freight Platform", layout="wide")
st.title("🚛 Lawson Freight Platform - Spruce Pine NC → Central GA")
st.markdown("**End-Dump Tinner Ops | 39ft / 24-ton Frameless**")

st.sidebar.header("Mission Control")
st.sidebar.write("**Priority Lane:** Spruce Pine, NC → Central GA (Kohler area)")
st.sidebar.write("**Trailer:** 39ft frameless end-dump (~24 tons)")
st.sidebar.write("**Goal:** Loaded miles + strong shipper relationships")

conn = sqlite3.connect('lawson_freight.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS leads 
             (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, address TEXT, notes TEXT, status TEXT, last_call TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS loads 
             (id INTEGER PRIMARY KEY, date TEXT, shipper TEXT, commodity TEXT, origin TEXT, dest TEXT, tons REAL, rate REAL, status TEXT, notes TEXT)''')

# Seed leads
c.execute("SELECT COUNT(*) FROM leads")
if c.fetchone()[0] == 0:
    hot_leads = [
        ("Sibelco Spruce Pine", "828-592-2780", "Highway 19E, Spruce Pine, NC 28777", "High-purity quartz + feldspar/mica", "New", str(datetime.now().date())),
        ("Covia", "1-800-243-9004", "7638 S Hwy 226, Spruce Pine, NC", "Feldspar & minerals", "New", str(datetime.now().date())),
        ("K-T Feldspar", "828-765-9621", "8342 Hwy 226 N, Spruce Pine, NC 28777", "Feldspar ops", "New", str(datetime.now().date())),
        ("Trimac Feldspar Trucking", "828-765-7491", "Local", "Intel", "New", str(datetime.now().date()))
    ]
    c.executemany("INSERT INTO leads VALUES (NULL,?,?,?,?,?,?)", hot_leads)
    conn.commit()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "👥 Leads CRM", "📝 Load Logger", "💰 Rate Calculator", "📄 BOL Generator"])

with tab1:
    st.header("Dashboard")
    col1, col2, col3 = st.columns(3)
    col1.metric("Hot Leads", 4)
    col2.metric("Loads This Week", 0)
    col3.metric("Lane Status", "Ready")
    st.info("Start by calling leads → log in CRM")

with tab2:
    st.header("Leads CRM")
    leads_df = pd.read_sql_query("SELECT * FROM leads", conn)
    st.dataframe(leads_df, use_container_width=True)
    if not leads_df.empty:
        lead_name = st.selectbox("Update Lead", leads_df['name'])
        notes = st.text_area("Call Notes")
        status = st.selectbox("Status", ["New", "Contacted", "Negotiating", "Booked"])
        if st.button("Save Update"):
            c.execute("UPDATE leads SET notes=?, status=?, last_call=? WHERE name=?", (notes, status, str(datetime.now().date()), lead_name))
            conn.commit()
            st.success("Saved!")
            st.rerun()

with tab3:
    st.header("Log Load")
    with st.form("load_form"):
        date = st.date_input("Date", datetime.now().date())
        shipper = st.selectbox("Shipper", leads_df['name'].tolist())
        commodity = st.text_input("Commodity")
        origin = st.text_input("Origin", "Spruce Pine, NC")
        dest = st.text_input("Dest", "Central GA")
        tons = st.number_input("Tons", 24.0)
        rate = st.number_input("Rate/ton $", 45.0)
        status = st.selectbox("Status", ["Pending", "Loaded"])
        notes = st.text_area("Notes")
        if st.form_submit_button("Log Load"):
            c.execute("INSERT INTO loads VALUES (NULL,?,?,?,?,?,?,?,?,?)", (str(date), shipper, commodity, origin, dest, tons, rate, status, notes))
            conn.commit()
            st.success("Load Logged!")
            st.rerun()

with tab4:
    st.header("Rate Calculator")
    miles = st.number_input("Miles", 300)
    tons = st.number_input("Tons", 24.0)
    rate = st.number_input("$/ton", 45.0)
    total = tons * rate
    st.metric("Revenue", f"${total:,.2f}")
    st.write(f"~${total/miles:.2f} per mile")

with tab5:
    st.header("BOL Preview")
    st.text("Lawson Freight - End Dump BOL\nReady for loads logged above.")

conn.close()