"""Opportunity desk — NC/GA market intel, honest sources, deadhead-ready storage.

Primary product path is local: call-ins, repeat shippers, board paste, and
curated lane seeds. BulkLoads live API is optional when secrets are present.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
from typing import Any, Callable

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Honest source taxonomy (shown to dispatch — never fake "live")
# ---------------------------------------------------------------------------

SOURCE_CALL_IN = "Call-in"
SOURCE_REPEAT = "Repeat shipper"
SOURCE_BOARD_PASTE = "Board paste"
SOURCE_LEAD = "Lead"
SOURCE_MANUAL = "Manual"
SOURCE_LANE_SEED_RETURN = "Lane Seed · Return"
SOURCE_LANE_SEED_OUTBOUND = "Lane Seed · Outbound"
SOURCE_BULKLOADS_LIVE = "BulkLoads · Live"
SOURCE_LEGACY_INTEL = "bulkloads_intel"  # migrated display → Lane Seed

OPPORTUNITY_SOURCE_CHOICES: list[str] = [
    SOURCE_CALL_IN,
    SOURCE_REPEAT,
    SOURCE_BOARD_PASTE,
    SOURCE_LEAD,
    SOURCE_MANUAL,
]

SOURCE_CSS_CLASS: dict[str, str] = {
    SOURCE_CALL_IN: "callin",
    SOURCE_REPEAT: "repeat",
    SOURCE_BOARD_PASTE: "paste",
    SOURCE_LEAD: "lead",
    SOURCE_MANUAL: "manual",
    SOURCE_LANE_SEED_RETURN: "seed",
    SOURCE_LANE_SEED_OUTBOUND: "seed",
    SOURCE_BULKLOADS_LIVE: "live",
    "BulkLoads": "seed",
    SOURCE_LEGACY_INTEL: "seed",
}


def display_source(source: str | None, *, live: bool = False) -> str:
    """Human-facing source label — never imply live API when data is curated."""
    raw = (source or SOURCE_MANUAL).strip()
    if live and raw.lower() in ("bulkloads", "api", SOURCE_BULKLOADS_LIVE.lower()):
        return SOURCE_BULKLOADS_LIVE
    legacy = {
        "bulkloads": SOURCE_LANE_SEED_OUTBOUND,
        "bulkloads_intel": SOURCE_LANE_SEED_RETURN,
        "bulkloads (placeholder)": SOURCE_LANE_SEED_RETURN,
        "manual": SOURCE_MANUAL,
        "board": SOURCE_BOARD_PASTE,
    }
    key = raw.lower()
    if key in legacy:
        return legacy[key]
    if raw in (SOURCE_LANE_SEED_RETURN, SOURCE_LANE_SEED_OUTBOUND, SOURCE_BULKLOADS_LIVE):
        return raw
    if "return" in key or "homebound" in key:
        return SOURCE_LANE_SEED_RETURN
    return raw or SOURCE_MANUAL


def source_badge_class(source: str | None) -> str:
    label = display_source(source)
    return SOURCE_CSS_CLASS.get(label, "manual")


# Curated NC/GA desk seeds — honest labels; mix return + outbound for ranking.
NC_GA_MARKET_INTEL: list[dict[str, Any]] = [
    # --- Return / homebound ---
    {
        "source": SOURCE_LANE_SEED_RETURN,
        "lane": "Macon, GA → Asheville, NC",
        "commodity": "Aggregate",
        "rate": "$46/ton",
        "contact": "Broker — return north",
        "posted": "Today",
        "notes": "Homebound corridor · end-dump · backhaul intent",
    },
    {
        "source": SOURCE_LANE_SEED_RETURN,
        "lane": "Central Georgia → Spruce Pine, NC",
        "commodity": "Sand",
        "rate": "$48/ton",
        "contact": "Shipper direct",
        "posted": "Today",
        "notes": "Return load · drops near home base · northbound",
    },
    {
        "source": SOURCE_LANE_SEED_RETURN,
        "lane": "Augusta, GA → Hickory, NC",
        "commodity": "Gravel",
        "rate": "$44/ton",
        "contact": "Broker — verify phone",
        "posted": "Today",
        "notes": "I-20 / I-26 pull · solid homebound direction",
    },
    {
        "source": SOURCE_LANE_SEED_RETURN,
        "lane": "Greenville, SC → Marion, NC",
        "commodity": "Clay",
        "rate": "$42/ton",
        "contact": "SC broker",
        "posted": "Yesterday",
        "notes": "Short empty from GA · mountain core drop",
    },
    {
        "source": SOURCE_LANE_SEED_RETURN,
        "lane": "Athens, GA → Boone, NC",
        "commodity": "Lime",
        "rate": "$45/ton",
        "contact": "Board paste",
        "posted": "Today",
        "notes": "Western NC corridor · verify plant access",
    },
    # --- Outbound ---
    {
        "source": SOURCE_LANE_SEED_OUTBOUND,
        "lane": "Spruce Pine, NC → Macon, GA",
        "commodity": "Feldspar",
        "rate": "$46–52/ton",
        "contact": "Broker — minerals",
        "posted": "Today",
        "notes": "End-dump preferred · 22–24t loads",
    },
    {
        "source": SOURCE_LANE_SEED_OUTBOUND,
        "lane": "Spruce Pine, NC → Augusta, GA",
        "commodity": "Mica",
        "rate": "$48/ton",
        "contact": "Shipper direct",
        "posted": "Yesterday",
        "notes": "Lined trailer required · weekly volume",
    },
    {
        "source": SOURCE_LANE_SEED_OUTBOUND,
        "lane": "Marion, NC → Central GA",
        "commodity": "Clay",
        "rate": "$44–47/ton",
        "contact": "Plant dispatch",
        "posted": "2 days ago",
        "notes": "Multiple pickups · minimize deadhead on return",
    },
    {
        "source": SOURCE_LANE_SEED_OUTBOUND,
        "lane": "Spruce Pine, NC → Kohler area, GA",
        "commodity": "Spar / Aggregate",
        "rate": "$50/ton",
        "contact": "Primary lane broker",
        "posted": "Today",
        "notes": "Primary L & P lane · 285 loaded mi baseline",
    },
    {
        "source": SOURCE_LANE_SEED_OUTBOUND,
        "lane": "Bakersville, NC → Atlanta, GA",
        "commodity": "Rock",
        "rate": "$42/ton",
        "contact": "Board paste",
        "posted": "3 days ago",
        "notes": "Verify weight · quarry access road",
    },
]

OPPORTUNITIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT DEFAULT 'Manual',
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
    source: str = SOURCE_MANUAL,
) -> int:
    cur = conn.execute(
        """INSERT INTO opportunities (source, lane, commodity, rate, contact, notes)
           VALUES (?,?,?,?,?,?)""",
        (display_source(source), lane, commodity, rate, contact, notes),
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
    source: str = SOURCE_LANE_SEED_RETURN,
) -> bool:
    """Insert intel listing only if same lane+commodity+source not already open."""
    src = display_source(source)
    existing = conn.execute(
        """
        SELECT id FROM opportunities
        WHERE source = ? AND lane = ? AND commodity = ? AND status = 'Open'
        LIMIT 1
        """,
        (src, lane, commodity),
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
        source=src,
    )
    return True


def seed_lane_intel(conn) -> tuple[int, int]:
    """Upsert curated NC/GA seeds. Returns (added, updated)."""
    ensure_opportunities_table(conn)
    added = updated = 0
    for item in NC_GA_MARKET_INTEL:
        is_new = upsert_market_intel(
            conn,
            lane=item["lane"],
            commodity=item["commodity"],
            rate=item["rate"],
            contact=item["contact"],
            notes=item.get("notes", ""),
            source=item.get("source", SOURCE_LANE_SEED_RETURN),
        )
        if is_new:
            added += 1
        else:
            updated += 1
    return added, updated


def fetch_opportunities(conn, *, open_only: bool = False) -> pd.DataFrame:
    try:
        sql = "SELECT * FROM opportunities"
        if open_only:
            sql += " WHERE status = 'Open' OR status IS NULL OR status = ''"
        sql += " ORDER BY created_at DESC"
        return pd.read_sql_query(sql, conn)
    except Exception:
        return pd.DataFrame()


def parse_lane(lane: str) -> tuple[str, str]:
    """Split 'Origin → Dest' into pair; empty origin if unparsable."""
    text = (lane or "").strip()
    for sep in ("→", "->", "—", " to "):
        if sep in text:
            a, b = [p.strip() for p in text.split(sep, 1)]
            return a, b
    return "", text


def rank_opportunities(
    opps_df: pd.DataFrame,
    *,
    home: str = "Spruce Pine, NC",
    current_location: str = "Central Georgia (Kohler area)",
    fuel_cost_per_mile: float = 0.72,
) -> list[dict[str, Any]]:
    """Deadhead-rank opportunities into display-ready card dicts."""
    from lp_helpers.deadhead import (
        estimate_return_benefit,
        opportunities_as_candidates,
        rank_return_candidates,
    )

    if opps_df is None or getattr(opps_df, "empty", True):
        return []

    ranked = rank_return_candidates(
        opportunities_as_candidates(opps_df),
        home=home,
        current_location=current_location,
    )
    cards: list[dict[str, Any]] = []
    for cand, sc in ranked:
        origin = str(cand.get("origin") or "")
        dest = str(cand.get("destination") or "")
        lane = str(cand.get("lane") or f"{origin} → {dest}")
        ben = estimate_return_benefit(
            sc,
            origin=origin,
            destination=dest,
            current_location=current_location,
            home=home,
            fuel_cost_per_mile=fuel_cost_per_mile,
        )
        cards.append(
            {
                "id": cand.get("id"),
                "lane": lane,
                "origin": origin,
                "destination": dest,
                "commodity": cand.get("commodity") or "Bulk",
                "rate": cand.get("rate") or "—",
                "contact": cand.get("contact") or "",
                "notes": cand.get("notes") or "",
                "source": display_source(cand.get("source")),
                "source_class": source_badge_class(cand.get("source")),
                "score": sc.score,
                "grade": sc.grade,
                "score_blurb": getattr(sc, "blurb", "") or "",
                "net_vs_empty": ben.get("net_benefit_vs_empty"),
                "empty_to_pickup_mi": ben.get("empty_to_pickup_mi"),
                "loaded_return_mi": ben.get("loaded_return_mi"),
                "benefit": ben,
                "scored": sc,
            }
        )
    return cards


def opp_card_html(card: dict[str, Any]) -> str:
    """HUD markup for one opportunity card (unsafe_allow_html)."""
    import html as html_lib

    src = html_lib.escape(str(card.get("source") or "Manual"))
    src_cls = html_lib.escape(str(card.get("source_class") or "manual"))
    commodity = html_lib.escape(str(card.get("commodity") or "Bulk"))
    lane = html_lib.escape(str(card.get("lane") or "—"))
    rate = html_lib.escape(str(card.get("rate") or "—"))
    contact = html_lib.escape(str(card.get("contact") or ""))
    notes = html_lib.escape(str(card.get("notes") or ""))
    grade = html_lib.escape(str(card.get("grade") or "—"))
    score = card.get("score")
    score_s = html_lib.escape(f"{score}" if score is not None else "—")
    net = card.get("net_vs_empty")
    net_s = f"${net:,.0f} vs pure empty" if isinstance(net, (int, float)) else ""
    net_s = html_lib.escape(net_s)

    return f"""
    <div class="lf-opp-card">
      <div class="lf-opp-top">
        <span class="lf-source-pill {src_cls}">{src}</span>
        <span class="lf-opp-grade">{grade} · {score_s}</span>
      </div>
      <div class="lf-opp-lane">{lane}</div>
      <div class="lf-opp-meta">
        <span class="lf-opp-commodity">{commodity}</span>
        <span class="lf-opp-rate">{rate}</span>
        {f'<span class="lf-opp-net">{net_s}</span>' if net_s else ''}
      </div>
      {f'<div class="lf-opp-contact">{contact}</div>' if contact else ''}
      {f'<div class="lf-opp-notes">{notes}</div>' if notes else ''}
    </div>
    """


def render_load_board_page(
    get_conn: Callable,
    clear_cache: Callable[[], None],
    commodity_options: list[str],
    primary_lane: dict[str, str],
    render_page_header: Callable[[str, str], None],
    render_lane_banner: Callable[[], None],
) -> None:
    """Legacy full Load Board tab UI (helpers module entrypoint)."""
    render_page_header(
        "Opportunity Desk",
        "Call-ins · lane seeds · deadhead rank · book to Logger",
    )
    render_lane_banner()

    st.markdown(
        '<div class="lf-section-header">📥 Log opportunity</div>',
        unsafe_allow_html=True,
    )
    with st.form("opportunity_form"):
        c1, c2 = st.columns(2)
        lane = c1.text_input(
            "Lane *",
            value=f"{primary_lane['origin']} → {primary_lane['destination']}",
        )
        commodity = c2.selectbox("Commodity", commodity_options)
        c3, c4, c5 = st.columns(3)
        rate = c3.text_input("Rate", placeholder="e.g. $48/ton or $1,200 flat")
        contact = c4.text_input("Contact", placeholder="Broker name / phone")
        source = c5.selectbox("Source", OPPORTUNITY_SOURCE_CHOICES)
        notes = st.text_area("Notes", placeholder="Pickup window, weight, equipment…")
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
                        source=source,
                    )
                    conn.commit()
                clear_cache()
                st.success(f"Opportunity saved — {lane}")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save opportunity: {exc}")

    st.markdown(
        '<div class="lf-section-header">🌱 Lane seeds (NC/GA)</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Curated corridor intel — not a live board feed. "
        "Optional BulkLoads API when secrets are configured."
    )
    if st.button("Seed / refresh lane intel", use_container_width=True, type="primary"):
        st.session_state["load_board_refreshed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            with closing(get_conn()) as conn:
                added, updated = seed_lane_intel(conn)
                conn.commit()
            clear_cache()
            st.success(f"Lane seeds · {added} new · {updated} refreshed")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.markdown(
        '<div class="lf-section-header">📋 Saved opportunities</div>',
        unsafe_allow_html=True,
    )
    try:
        with closing(get_conn()) as conn:
            opps_df = fetch_opportunities(conn)
    except Exception as exc:
        st.warning(f"Could not load opportunities: {exc}")
        opps_df = pd.DataFrame()

    if opps_df.empty:
        st.info("No opportunities yet. Log a call-in or seed lane intel.")
    else:
        if "source" in opps_df.columns:
            opps_df = opps_df.copy()
            opps_df["source"] = opps_df["source"].map(lambda s: display_source(s))
        display_cols = ["lane", "commodity", "rate", "contact", "source", "status", "created_at"]
        show_cols = [c for c in display_cols if c in opps_df.columns]
        st.dataframe(opps_df[show_cols], use_container_width=True, hide_index=True)
