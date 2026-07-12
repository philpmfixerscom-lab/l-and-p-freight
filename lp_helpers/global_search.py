"""
Global Search & Command Bar — unified search across loads/leads/customers/POs
with recent + suggested queries and quick chips.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from lp_helpers.database import get_conn, get_setting, set_setting


# ===========================================================================
# Search configuration
# ===========================================================================

SEARCH_CATEGORIES = [
    "loads",
    "leads",
    "customers",
    "purchase_orders",
    "documents",
    "settlements",
    "compliance",
]

SEARCH_CHIPS = [
    {"label": "📦 Recent Loads", "query": "recent loads", "screen": "Log Load"},
    {"label": "📇 Hot Leads", "query": "hot leads", "screen": "Leads"},
    {"label": "💰 Pending Settlements", "query": "pending settlements", "screen": "Billing & Pay"},
    {"label": "📋 Open POs", "query": "open purchase orders", "screen": "Portal"},
    {"label": "📁 Documents", "query": "documents", "screen": "Documents"},
    {"label": "✅ Compliance Due", "query": "compliance due soon", "screen": "Compliance"},
    {"label": "📊 Analytics", "query": "analytics", "screen": "Analytics"},
    {"label": "🚛 Driver App", "query": "driver", "screen": "Driver"},
]


# ===========================================================================
# Search history (stored in app_settings)
# ===========================================================================

SEARCH_HISTORY_KEY = "global_search_history"
MAX_HISTORY = 10


def get_search_history() -> list[str]:
    """Get recent search queries from settings."""
    raw = get_setting(SEARCH_HISTORY_KEY, "[]")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def add_to_search_history(query: str) -> None:
    """Add a query to search history, deduplicating and capping at MAX_HISTORY."""
    history = get_search_history()
    # Remove duplicate if exists
    history = [q for q in history if q.lower() != query.lower()]
    # Add to front
    history.insert(0, query)
    # Cap
    history = history[:MAX_HISTORY]
    set_setting(SEARCH_HISTORY_KEY, json.dumps(history))


def clear_search_history() -> None:
    """Clear all search history."""
    set_setting(SEARCH_HISTORY_KEY, "[]")


# ===========================================================================
# Search execution
# ===========================================================================

def execute_search(query: str) -> dict[str, list[dict[str, Any]]]:
    """
    Execute a unified search across all entities.
    Returns dict of category -> list of result dicts.
    """
    results: dict[str, list[dict[str, Any]]] = {
        "loads": [],
        "leads": [],
        "customers": [],
        "purchase_orders": [],
        "documents": [],
        "settlements": [],
        "compliance": [],
    }

    if not query or len(query.strip()) < 1:
        return results

    q = query.strip().lower()
    conn = get_conn()

    # Search loads
    try:
        loads = conn.execute(
            """
            SELECT id, bol_number, shipper, commodity, origin, destination,
                   total_revenue, status, pickup_date
            FROM loads
            WHERE LOWER(bol_number) LIKE ? OR LOWER(shipper) LIKE ?
               OR LOWER(commodity) LIKE ? OR LOWER(origin) LIKE ?
               OR LOWER(destination) LIKE ? OR LOWER(status) LIKE ?
            ORDER BY pickup_date DESC LIMIT 10
            """,
            tuple([f"%{q}%"] * 6),
        ).fetchall()
        for row in loads:
            results["loads"].append({
                "id": int(row["id"]),
                "label": f"{row['bol_number']} — {row['shipper']} ({row['commodity']})",
                "subtitle": f"{row.get('origin', '')} → {row.get('destination', '')} · ${float(row.get('total_revenue', 0)):,.0f}",
                "status": row["status"],
                "screen": "Log Load",
                "icon": "🚚",
            })
    except Exception:
        pass

    # Search leads
    try:
        leads = conn.execute(
            """
            SELECT id, company, contact_name, phone, commodity_focus, status, priority
            FROM leads
            WHERE LOWER(company) LIKE ? OR LOWER(contact_name) LIKE ?
               OR LOWER(commodity_focus) LIKE ? OR LOWER(phone) LIKE ?
            ORDER BY priority, company LIMIT 10
            """,
            tuple([f"%{q}%"] * 4),
        ).fetchall()
        for row in leads:
            results["leads"].append({
                "id": int(row["id"]),
                "label": row["company"],
                "subtitle": f"{row.get('contact_name', '')} · {row.get('phone', '')} · {row.get('commodity_focus', '')}",
                "status": row["status"],
                "screen": "Leads",
                "icon": "📇",
            })
    except Exception:
        pass

    # Search customers
    try:
        customers = conn.execute(
            """
            SELECT id, name, contact_name, phone, email, notes
            FROM customers
            WHERE LOWER(name) LIKE ? OR LOWER(contact_name) LIKE ?
               OR LOWER(phone) LIKE ? OR LOWER(email) LIKE ?
            ORDER BY name LIMIT 10
            """,
            tuple([f"%{q}%"] * 4),
        ).fetchall()
        for row in customers:
            results["customers"].append({
                "id": int(row["id"]),
                "label": row["name"],
                "subtitle": f"{row.get('contact_name', '')} · {row.get('phone', '')} · {row.get('email', '')}",
                "status": "Active",
                "screen": "Portal",
                "icon": "🏢",
            })
    except Exception:
        pass

    # Search purchase orders
    try:
        pos = conn.execute(
            """
            SELECT po.id, po.po_number, po.status, po.total_estimated_revenue,
                   c.name as customer_name
            FROM purchase_orders po
            LEFT JOIN customers c ON po.customer_id = c.id
            WHERE LOWER(po.po_number) LIKE ? OR LOWER(c.name) LIKE ?
               OR LOWER(po.status) LIKE ?
            ORDER BY po.created_at DESC LIMIT 10
            """,
            tuple([f"%{q}%"] * 3),
        ).fetchall()
        for row in pos:
            results["purchase_orders"].append({
                "id": int(row["id"]),
                "label": f"PO {row['po_number']} — {row.get('customer_name', '')}",
                "subtitle": f"Status: {row['status']} · Est. ${float(row.get('total_estimated_revenue', 0)):,.0f}",
                "status": row["status"],
                "screen": "Portal",
                "icon": "📋",
            })
    except Exception:
        pass

    # Search documents
    try:
        docs = conn.execute(
            """
            SELECT id, original_name, category, description, mime_type
            FROM documents
            WHERE LOWER(original_name) LIKE ? OR LOWER(description) LIKE ?
               OR LOWER(category) LIKE ? OR LOWER(tags) LIKE ?
            ORDER BY uploaded_at DESC LIMIT 10
            """,
            tuple([f"%{q}%"] * 4),
        ).fetchall()
        for row in docs:
            results["documents"].append({
                "id": int(row["id"]),
                "label": row["original_name"],
                "subtitle": f"{row.get('category', '')} · {row.get('description', '') or ''}",
                "status": row.get("mime_type", ""),
                "screen": "Documents",
                "icon": "📁",
            })
    except Exception:
        pass

    # Search settlements
    try:
        setts = conn.execute(
            """
            SELECT s.id, s.driver_name, s.total_pay, s.status, l.bol_number, l.shipper
            FROM settlements s
            LEFT JOIN loads l ON s.load_id = l.id
            WHERE LOWER(s.driver_name) LIKE ? OR LOWER(l.bol_number) LIKE ?
               OR LOWER(l.shipper) LIKE ? OR LOWER(s.status) LIKE ?
            ORDER BY s.created_at DESC LIMIT 10
            """,
            tuple([f"%{q}%"] * 4),
        ).fetchall()
        for row in setts:
            results["settlements"].append({
                "id": int(row["id"]),
                "label": f"Settlement #{row['id']} — {row.get('bol_number', '')}",
                "subtitle": f"Driver: {row.get('driver_name', '')} · ${float(row.get('total_pay', 0)):,.0f}",
                "status": row["status"],
                "screen": "Billing & Pay",
                "icon": "💰",
            })
    except Exception:
        pass

    # Search compliance
    try:
        comp = conn.execute(
            """
            SELECT id, item, status, due_date, notes
            FROM compliance
            WHERE LOWER(item) LIKE ? OR LOWER(status) LIKE ?
               OR LOWER(notes) LIKE ?
            ORDER BY due_date LIMIT 10
            """,
            tuple([f"%{q}%"] * 3),
        ).fetchall()
        for row in comp:
            results["compliance"].append({
                "id": int(row["id"]),
                "label": row["item"],
                "subtitle": f"Status: {row['status']} · Due: {row.get('due_date', '—')}",
                "status": row["status"],
                "screen": "Compliance",
                "icon": "✅",
            })
    except Exception:
        pass

    conn.close()
    return results


# ===========================================================================
# UI Render
# ===========================================================================

def render_global_search_bar() -> None:
    """Render the global search bar at the top of the app."""
    st.markdown(
        """
        <style>
        .lf-search-container {
            position: relative;
            margin-bottom: 0.5rem;
        }
        .lf-search-input {
            width: 100%;
            padding: 0.75rem 1rem 0.75rem 2.5rem;
            border: 2px solid var(--lf-border);
            border-radius: 14px;
            font-size: 1rem;
            background: var(--lf-card);
            color: var(--lf-text);
            outline: none;
            transition: border-color 0.15s ease;
        }
        .lf-search-input:focus {
            border-color: var(--lf-orange);
        }
        .lf-search-icon {
            position: absolute;
            left: 0.8rem;
            top: 50%;
            transform: translateY(-50%);
            font-size: 1.2rem;
            color: var(--lf-muted);
        }
        .lf-search-shortcut {
            position: absolute;
            right: 0.8rem;
            top: 50%;
            transform: translateY(-50%);
            font-size: 0.7rem;
            color: var(--lf-muted);
            background: var(--lf-bg);
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            border: 1px solid var(--lf-border);
        }
        .lf-search-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin: 0.5rem 0;
        }
        .lf-search-chip {
            padding: 0.3rem 0.7rem;
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 20px;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.12s ease;
            color: var(--lf-text);
        }
        .lf-search-chip:hover {
            border-color: var(--lf-orange);
            background: rgba(234, 88, 12, 0.06);
        }
        .lf-search-result {
            padding: 0.6rem 0.8rem;
            border-bottom: 1px solid var(--lf-border);
            cursor: pointer;
            transition: background 0.1s ease;
        }
        .lf-search-result:hover {
            background: rgba(234, 88, 12, 0.04);
        }
        .lf-search-result:last-child {
            border-bottom: none;
        }
        .lf-search-result-icon {
            font-size: 1.2rem;
            margin-right: 0.5rem;
        }
        .lf-search-result-label {
            font-weight: 600;
            color: var(--lf-text);
        }
        .lf-search-result-subtitle {
            font-size: 0.8rem;
            color: var(--lf-muted);
        }
        .lf-search-result-status {
            font-size: 0.7rem;
            padding: 0.1rem 0.4rem;
            border-radius: 4px;
            background: var(--lf-bg);
            color: var(--lf-muted);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Search input
    search_query = st.text_input(
        "🔍 Search loads, leads, customers, POs...",
        key="global_search_input",
        placeholder="Search loads, leads, customers, POs...",
        label_visibility="collapsed",
    )

    # Quick chips
    st.markdown(
        "<div class='lf-search-chips'>" +
        "".join(
            f"<span class='lf-search-chip' onclick=\"document.querySelector('[data-testid=stTextInput] input').value='{chip['query']}'; document.querySelector('[data-testid=stTextInput] input').dispatchEvent(new Event('input', {{bubbles:true}}));\">{chip['label']}</span>"
            for chip in SEARCH_CHIPS
        ) +
        "</div>",
        unsafe_allow_html=True,
    )

    # Show recent searches if no query
    if not search_query:
        history = get_search_history()
        if history:
            st.markdown(
                "<div style='font-size:0.8rem;color:var(--lf-muted);margin-bottom:0.3rem;'>Recent searches:</div>"
                + "".join(
                    f"<span class='lf-search-chip'>{h}</span>"
                    for h in history
                ),
                unsafe_allow_html=True,
            )
            if st.button("Clear history", key="clear_search_hist", use_container_width=True, type="secondary"):
                clear_search_history()
                st.rerun()
        return

    # Execute search
    results = execute_search(search_query)
    total_results = sum(len(v) for v in results.values())

    if total_results == 0:
        st.info(f"No results found for '{search_query}'")
        return

    # Save to history
    add_to_search_history(search_query)

    st.markdown(f"**{total_results}** result(s) for '{search_query}'")

    # Display results by category
    category_labels = {
        "loads": "🚚 Loads",
        "leads": "📇 Leads",
        "customers": "🏢 Customers",
        "purchase_orders": "📋 Purchase Orders",
        "documents": "📁 Documents",
        "settlements": "💰 Settlements",
        "compliance": "✅ Compliance",
    }

    for cat_key, cat_label in category_labels.items():
        items = results.get(cat_key, [])
        if not items:
            continue

        st.markdown(f"##### {cat_label} ({len(items)})")
        for item in items:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(
                    f"<div class='lf-search-result'>"
                    f"<div><span class='lf-search-result-icon'>{item.get('icon', '•')}</span>"
                    f"<span class='lf-search-result-label'>{item['label']}</span></div>"
                    f"<div class='lf-search-result-subtitle'>{item.get('subtitle', '')}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with col2:
                if st.button("Go →", key=f"search_go_{cat_key}_{item['id']}", use_container_width=True):
                    st.session_state["screen"] = item["screen"]
                    st.rerun()


def render_search_results_modal() -> None:
    """Render a compact search results overlay (for command-bar style use)."""
    # This is a lightweight version that can be embedded in any page
    search_query = st.session_state.get("global_search_input", "")

    if not search_query or len(search_query.strip()) < 2:
        return

    results = execute_search(search_query)
    total = sum(len(v) for v in results.values())

    if total == 0:
        st.caption(f"No results for '{search_query}'")
        return

    # Show top 5 results across all categories
    all_results = []
    for cat, items in results.items():
        for item in items:
            all_results.append({**item, "category": cat})

    all_results.sort(key=lambda x: x.get("id", 0), reverse=True)

    for item in all_results[:5]:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(
                f"<div style='padding:0.3rem 0;'>"
                f"<span style='font-size:0.9rem;'>{item.get('icon', '•')}</span> "
                f"<strong>{item['label']}</strong>"
                f"<br><span style='font-size:0.8rem;color:var(--lf-muted);'>{item.get('subtitle', '')}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col2:
            if st.button("→", key=f"search_q_{item['category']}_{item['id']}", use_container_width=True):
                st.session_state["screen"] = item["screen"]
                st.rerun()