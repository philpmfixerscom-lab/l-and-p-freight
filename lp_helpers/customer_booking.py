"""
Customer Self-Serve Booking — let customers submit a dispatch request
that flows straight into Log Load. Extends the existing "New Dispatch Request"
in the Customer Portal.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from lp_helpers.database import get_conn, generate_bol_number


# ===========================================================================
# Data models
# ===========================================================================

DISPATCH_REQUEST_STATUSES = [
    "Pending Review",
    "Approved",
    "Scheduled",
    "In Transit",
    "Delivered",
    "Cancelled",
    "Declined",
]


# ===========================================================================
# Database operations
# ===========================================================================

def create_dispatch_request(
    customer_id: int,
    po_number: str,
    commodity: str,
    weight_tons: float,
    origin: str,
    destination: str,
    pickup_date: str,
    delivery_date: str | None = None,
    notes: str = "",
    contact_name: str = "",
    contact_phone: str = "",
) -> int:
    """
    Create a new dispatch request from a customer.
    This creates a PO + po_load entry that flows into Log Load.
    Returns the dispatch_request_id.
    """
    conn = get_conn()

    # Create or find PO
    existing_po = conn.execute(
        "SELECT id FROM purchase_orders WHERE po_number = ? AND customer_id = ?",
        (po_number, customer_id),
    ).fetchone()

    if existing_po:
        po_id = int(existing_po["id"])
    else:
        conn.execute(
            "INSERT INTO purchase_orders (customer_id, po_number, status, notes) VALUES (?,?,?,?)",
            (customer_id, po_number, "Open", f"Self-serve booking: {notes}"),
        )
        conn.commit()
        po_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    # Create a placeholder load entry
    bol = generate_bol_number()
    conn.execute(
        """
        INSERT INTO loads (
            bol_number, shipper, commodity, weight_tons, origin, destination,
            pickup_date, delivery_date, rate_per_ton, total_revenue, status, notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            bol,
            f"Customer #{customer_id}",
            commodity,
            weight_tons,
            origin,
            destination,
            pickup_date,
            delivery_date or pickup_date,
            0.0,  # rate to be confirmed
            0.0,  # revenue to be confirmed
            "Pending",
            f"Self-serve dispatch request. Contact: {contact_name} ({contact_phone}). {notes}",
        ),
    )
    conn.commit()
    load_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    # Link to PO
    conn.execute(
        """
        INSERT INTO po_loads (po_id, load_id, sequence, scheduled_pickup_date, scheduled_delivery_date, status, notes)
        VALUES (?,?,?,?,?,?,?)
        """,
        (po_id, load_id, 1, pickup_date, delivery_date or pickup_date, "Pending Review", notes),
    )
    conn.commit()

    # Log the dispatch request
    conn.execute(
        """
        INSERT INTO dispatch_requests (customer_id, po_id, load_id, bol_number, status, notes)
        VALUES (?,?,?,?,?,?)
        """,
        (customer_id, po_id, load_id, bol, "Pending Review", notes),
    )
    conn.commit()

    request_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.close()
    return request_id


def ensure_dispatch_requests_table() -> None:
    """Create the dispatch_requests table if it doesn't exist."""
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dispatch_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            po_id INTEGER,
            load_id INTEGER,
            bol_number TEXT,
            status TEXT DEFAULT 'Pending Review',
            contact_name TEXT,
            contact_phone TEXT,
            commodity TEXT,
            weight_tons REAL,
            origin TEXT,
            destination TEXT,
            pickup_date TEXT,
            delivery_date TEXT,
            notes TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (po_id) REFERENCES purchase_orders(id),
            FOREIGN KEY (load_id) REFERENCES loads(id)
        )
        """,
    )
    conn.commit()
    conn.close()


def fetch_dispatch_requests(customer_id: int | None = None, status: str | None = None) -> pd.DataFrame:
    """Fetch dispatch requests, optionally filtered by customer and/or status."""
    conn = get_conn()
    q = """
        SELECT dr.*, c.name as customer_name, c.contact_name as cust_contact, c.phone as cust_phone
        FROM dispatch_requests dr
        LEFT JOIN customers c ON dr.customer_id = c.id
    """
    params: list[Any] = []
    conditions = []
    if customer_id is not None:
        conditions.append("dr.customer_id = ?")
        params.append(customer_id)
    if status is not None:
        conditions.append("dr.status = ?")
        params.append(status)
    if conditions:
        q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY dr.created_at DESC"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def update_dispatch_request_status(request_id: int, status: str, reviewed_by: str = "Dispatcher") -> None:
    """Update the status of a dispatch request and sync to linked load."""
    conn = get_conn()
    conn.execute(
        """
        UPDATE dispatch_requests
        SET status = ?, reviewed_by = ?, reviewed_at = datetime('now')
        WHERE id = ?
        """,
        (status, reviewed_by, request_id),
    )

    # Sync status to linked load
    req = conn.execute(
        "SELECT load_id, bol_number FROM dispatch_requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    if req and req["load_id"]:
        load_status_map = {
            "Approved": "Scheduled",
            "Scheduled": "Scheduled",
            "In Transit": "In Transit",
            "Delivered": "Delivered",
            "Cancelled": "Cancelled",
            "Declined": "Cancelled",
        }
        new_load_status = load_status_map.get(status, "Pending")
        conn.execute(
            "UPDATE loads SET status = ? WHERE id = ?",
            (new_load_status, int(req["load_id"])),
        )
        # Also update po_loads
        conn.execute(
            "UPDATE po_loads SET status = ? WHERE load_id = ?",
            (new_load_status, int(req["load_id"])),
        )

    conn.commit()
    conn.close()


def get_pending_dispatch_count() -> int:
    """Get count of pending dispatch requests needing review."""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM dispatch_requests WHERE status = 'Pending Review'",
    ).fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0


# ===========================================================================
# UI Render — Customer-facing booking form
# ===========================================================================

def render_customer_booking_form(customer_id: int, customer_name: str) -> None:
    """Render the self-serve booking form for a customer."""
    st.markdown("#### 📋 New Dispatch Request")
    st.caption("Submit a load request — it will be reviewed and scheduled by our dispatch team.")

    with st.form("customer_booking_form"):
        col1, col2 = st.columns(2)
        with col1:
            po_number = st.text_input("PO Number *", placeholder="PO-2026-001", value=f"PO-{date.today().strftime('%Y%m%d')}-")
            commodity = st.selectbox(
                "Commodity *",
                ["Feldspar", "Mica", "Spar", "Clay", "Rock", "Lime", "Fertilizer",
                 "Sand", "Gravel", "Aggregate", "Corn", "Soybean", "Other"],
            )
            weight = st.number_input("Weight (tons) *", 1.0, 24.0, 22.0, 0.5)
        with col2:
            origin = st.text_input("Origin *", value="Spruce Pine, NC")
            destination = st.text_input("Destination *", value="Central Georgia (Kohler area)")
            pickup = st.date_input("Pickup Date *", value=date.today() + timedelta(days=2))
            delivery = st.date_input("Delivery Date", value=date.today() + timedelta(days=5))

        contact_name = st.text_input("Contact Name", value=customer_name)
        contact_phone = st.text_input("Contact Phone")
        notes = st.text_area("Special Instructions / Notes")

        submitted = st.form_submit_button("Submit Dispatch Request", type="primary", use_container_width=True)

    if submitted:
        if not po_number.strip():
            st.error("PO Number is required.")
            return
        if not commodity:
            st.error("Commodity is required.")
            return
        if not origin.strip() or not destination.strip():
            st.error("Origin and destination are required.")
            return

        try:
            request_id = create_dispatch_request(
                customer_id=customer_id,
                po_number=po_number.strip(),
                commodity=commodity,
                weight_tons=weight,
                origin=origin.strip(),
                destination=destination.strip(),
                pickup_date=str(pickup),
                delivery_date=str(delivery),
                notes=notes,
                contact_name=contact_name,
                contact_phone=contact_phone,
            )
            st.success(f"✅ Dispatch request submitted! Reference: #{request_id}")
            st.info("Our team will review and confirm shortly. You'll see updates in 'My Loads'.")
            st.balloons()
        except Exception as e:
            st.error(f"Failed to submit request: {e}")


# ===========================================================================
# UI Render — Dispatcher review panel
# ===========================================================================

def render_dispatcher_review_panel() -> None:
    """Render the dispatcher panel for reviewing and approving dispatch requests."""
    st.markdown("#### 📥 Incoming Dispatch Requests")

    pending_count = get_pending_dispatch_count()
    if pending_count > 0:
        st.warning(f"**{pending_count}** request(s) pending review")

    # Filter tabs
    tab_all, tab_pending, tab_approved, tab_history = st.tabs(
        ["All", f"Pending Review ({pending_count})", "Approved/Scheduled", "History"]
    )

    with tab_all:
        df = fetch_dispatch_requests()
        if df.empty:
            st.info("No dispatch requests yet.")
        else:
            _render_dispatch_table(df, show_review=True)

    with tab_pending:
        df = fetch_dispatch_requests(status="Pending Review")
        if df.empty:
            st.success("No pending requests — all caught up!")
        else:
            _render_dispatch_table(df, show_review=True)

    with tab_approved:
        df = fetch_dispatch_requests(status="Approved")
        if df.empty:
            st.info("No approved requests.")
        else:
            _render_dispatch_table(df, show_review=False)

    with tab_history:
        df = fetch_dispatch_requests()
        if not df.empty:
            df = df[~df["status"].isin(["Pending Review"])]
        if df.empty:
            st.info("No historical requests.")
        else:
            _render_dispatch_table(df, show_review=False)


def _render_dispatch_table(df: pd.DataFrame, show_review: bool = False) -> None:
    """Render a table of dispatch requests with optional review actions."""
    for _, row in df.iterrows():
        status_color = {
            "Pending Review": "amber",
            "Approved": "green",
            "Scheduled": "blue",
            "In Transit": "orange",
            "Delivered": "green",
            "Cancelled": "red",
            "Declined": "red",
        }.get(row["status"], "gray")

        st.markdown(
            f"<div class='lf-card'>"
            f"<div class='lf-row'><b>#{row['id']}</b>"
            f"<span class='lf-pill {status_color}'><span class='lf-dot'></span>{row['status']}</span></div>"
            f"<div class='lf-muted'>{row.get('customer_name', '—')} · {row.get('commodity', '—')} · "
            f"{row.get('weight_tons', 0)}t</div>"
            f"<div class='lf-muted'>{row.get('origin', '')} → {row.get('destination', '')}</div>"
            f"<div class='lf-muted'>Pickup: {row.get('pickup_date', '—')} · "
            f"BOL: {row.get('bol_number', '—')}</div>"
            f"<div class='lf-muted'>Contact: {row.get('contact_name', row.get('cust_contact', '—'))} · "
            f"{row.get('contact_phone', row.get('cust_phone', '—'))}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if show_review and row["status"] == "Pending Review":
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("✅ Approve", key=f"dr_approve_{row['id']}", use_container_width=True):
                    update_dispatch_request_status(int(row["id"]), "Approved")
                    st.success(f"Request #{row['id']} approved — load scheduled.")
                    st.rerun()
            with col_b:
                if st.button("📅 Schedule", key=f"dr_sched_{row['id']}", use_container_width=True):
                    update_dispatch_request_status(int(row["id"]), "Scheduled")
                    st.success(f"Request #{row['id']} scheduled.")
                    st.rerun()
            with col_c:
                if st.button("❌ Decline", key=f"dr_decline_{row['id']}", use_container_width=True, type="secondary"):
                    update_dispatch_request_status(int(row["id"]), "Declined")
                    st.info(f"Request #{row['id']} declined.")
                    st.rerun()

        if row.get("notes"):
            st.caption(f"📝 {row['notes']}")