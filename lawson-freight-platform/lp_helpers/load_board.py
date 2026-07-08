"""BulkLoads.com load board — opportunities storage and NC/GA market intel."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
from typing import Any, Callable

import pandas as pd
import streamlit as st

# Placeholder market intel — refresh button updates timestamp; future: BulkLoads API scrape
NC_GA_MARKET_INTEL: list[dict[str, Any]] = [
    {
        "source": "BulkLoads (placeholder)",
        "lane": "Spruce Pine, NC → Macon, GA",
        "commodity": "Feldspar",
        "rate": "$46–52/ton",
        "contact": "Broker — (828) 555-0142",
        "posted": "Today",
        "notes": "End-dump preferred · 22–24t loads",
    },
    {
        "source": "BulkLoads (placeholder)",
        "lane": "Spruce Pine, NC → Augusta, GA",
        "commodity": "Mica",
        "rate": "$48/ton",
        "contact": "Shipper direct",
        "posted": "Yesterday",
        "notes": "Lined trailer required · weekly volume",
    },
    {
        "source": "BulkLoads (placeholder)",
        "lane": "Marion, NC → Central GA",
        "commodity": "Clay",
        "rate": "$44–47/ton",
        "contact": "Covia dispatch",
        "posted": "2 days ago",
        "notes": "Multiple pickups · minimize deadhead on return",
    },
    {
        "source": "BulkLoads (placeholder)",
        "lane": "Spruce Pine, NC → Kohler area, GA",
        "commodity": "Spar / Aggregate",
        "rate": "$50/ton",
        "contact": "Trimac broker",
        "posted": "Today",
        "notes": "Primary L & P lane · 285 loaded mi baseline",
    },
    {
        "source": "BulkLoads (placeholder)",
        "lane": "Bakersville, NC → Atlanta, GA",
        "commodity": "Rock",
        "rate": "$42/ton",
        "contact": "Load board poster",
        "posted": "3 days ago",
        "notes": "Verify weight · quarry access road",
    },
]

OPPORTUNITIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT DEFAULT 'manual',
    lane TEXT NOT NULL,
    commodity TEXT,
    rate TEXT,
    contact TEXT,
    notes TEXT,
    status TEXT DEFAULT 'Open',
    created_at TEXT DEFAULT (datetime('now')),
    refreshed_at TEXT
);
"""


def ensure_opportunities_table(conn) -> None:
    conn.executescript(OPPORTUNITIES_SCHEMA)


def insert_opportunity(
    conn,
    *,
    lane: str,
    commodity: str,
    rate: str,
    contact: str,
    notes: str = "",
    source: str = "manual",
) -> int:
    cur = conn.execute(
        """INSERT INTO opportunities (source, lane, commodity, rate, contact, notes)
           VALUES (?,?,?,?,?,?)""",
        (source, lane, commodity, rate, contact, notes),
    )
    return cur.lastrowid


def upsert_market_intel(
    conn,
    *,
    lane: str,
    commodity: str,
    rate: str,
    contact: str,
    notes: str = "",
    source: str = "bulkloads_intel",
) -> bool:
    """Insert intel listing only if same lane+commodity+source not already open."""
    existing = conn.execute(
        """
        SELECT id FROM opportunities
        WHERE source = ? AND lane = ? AND commodity = ? AND status = 'Open'
        LIMIT 1
        """,
        (source, lane, commodity),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE opportunities
            SET rate = ?, contact = ?, notes = ?, refreshed_at = datetime('now')
            WHERE id = ?
            """,
            (rate, contact, notes, existing[0]),
        )
        return False
    insert_opportunity(
        conn,
        lane=lane,
        commodity=commodity,
        rate=rate,
        contact=contact,
        notes=notes,
        source=source,
    )
    return True


def fetch_opportunities(conn) -> pd.DataFrame:
    try:
        return pd.read_sql_query(
            "SELECT * FROM opportunities ORDER BY created_at DESC",
            conn,
        )
    except Exception:
        return pd.DataFrame()


def render_load_board_page(
    get_conn: Callable,
    clear_cache: Callable[[], None],
    commodity_options: list[str],
    primary_lane: dict[str, str],
    render_page_header: Callable[[str, str], None],
    render_lane_banner: Callable[[], None],
) -> None:
    """Full Load Board tab UI."""
    render_page_header("Load Board", "Track BulkLoads opportunities on your NC → GA lanes")
    render_lane_banner()

    st.markdown('<div class="lf-section-header">📥 Log BulkLoads Opportunity</div>', unsafe_allow_html=True)
    with st.form("opportunity_form"):
        c1, c2 = st.columns(2)
        lane = c1.text_input("Lane *", value=f"{primary_lane['origin']} → {primary_lane['destination']}")
        commodity = c2.selectbox("Commodity", commodity_options)
        c3, c4 = st.columns(2)
        rate = c3.text_input("Rate", placeholder="e.g. $48/ton or $1,200 flat")
        contact = c4.text_input("Contact", placeholder="Broker name / phone / email")
        notes = st.text_area("Notes", placeholder="Pickup window, weight, equipment requirements…")
        submitted = st.form_submit_button("SAVE OPPORTUNITY", use_container_width=True)

    if submitted:
        if not lane.strip():
            st.error("Lane is required.")
        else:
            try:
                with closing(get_conn()) as conn:
                    insert_opportunity(
                        conn,
                        lane=lane.strip(),
                        commodity=commodity,
                        rate=rate.strip(),
                        contact=contact.strip(),
                        notes=notes.strip(),
                    )
                    conn.commit()
                clear_cache()
                st.success(f"Opportunity saved — {lane}")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save opportunity: {exc}")

    st.markdown('<div class="lf-section-header">🔄 NC/GA End-Dump Market Intel</div>', unsafe_allow_html=True)
    st.caption("Placeholder intel for Spruce Pine → Central GA lanes. Future: BulkLoads API integration.")

    if st.button("Refresh NC/GA End-Dump Loads", use_container_width=True, type="primary"):
        st.session_state["load_board_refreshed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Future: fetch live BulkLoads listings and INSERT with source='bulkloads'

    refreshed = st.session_state.get("load_board_refreshed", "Not refreshed this session")
    st.info(f"Market snapshot · last refresh: **{refreshed}** · {len(NC_GA_MARKET_INTEL)} listings")

    for item in NC_GA_MARKET_INTEL:
        st.markdown(
            f"""
            <div class="lf-panel" style="margin-bottom:0.5rem;padding:0.75rem 1rem;">
                <strong>{item['commodity']}</strong> · {item['lane']}<br/>
                <span style="color:#e85d04;font-weight:700;">{item['rate']}</span>
                · {item['contact']} · Posted {item['posted']}<br/>
                <span style="font-size:0.85rem;color:#94a3b8;">{item['notes']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="lf-section-header">📋 Saved Opportunities</div>', unsafe_allow_html=True)
    try:
        with closing(get_conn()) as conn:
            opps_df = fetch_opportunities(conn)
    except Exception as exc:
        st.warning(f"Could not load opportunities: {exc}")
        opps_df = pd.DataFrame()

    if opps_df.empty:
        st.info("No opportunities logged yet. Add one above or refresh market intel.")
    else:
        display_cols = ["lane", "commodity", "rate", "contact", "status", "created_at"]
        show_cols = [c for c in display_cols if c in opps_df.columns]
        st.dataframe(opps_df[show_cols], use_container_width=True, hide_index=True)

        with st.expander("Import market listing to opportunities"):
            labels = [f"{r['commodity']} — {r['lane']}" for r in NC_GA_MARKET_INTEL]
            pick = st.selectbox("Listing", labels)
            if st.button("SAVE LISTING TO DB", use_container_width=True):
                idx = labels.index(pick)
                row = NC_GA_MARKET_INTEL[idx]
                try:
                    with closing(get_conn()) as conn:
                        insert_opportunity(
                            conn,
                            lane=row["lane"],
                            commodity=row["commodity"],
                            rate=row["rate"],
                            contact=row["contact"],
                            notes=row.get("notes", ""),
                            source="bulkloads_placeholder",
                        )
                        conn.commit()
                    clear_cache()
                    st.success("Listing saved to opportunities.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Import failed: {exc}")