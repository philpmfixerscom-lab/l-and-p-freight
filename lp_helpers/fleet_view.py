"""Multi-trailer / multi-driver fleet board for dispatch.

Uses assets table (trucks, trailers, drivers) + load assignments (asset_id)
to show who is hauling what across the fleet.
"""

from __future__ import annotations

from contextlib import closing
from typing import Any, Callable

import pandas as pd
import streamlit as st

from lp_helpers.database import get_conn

# Expanded seed used when assets table is empty or missing drivers
FLEET_SEED: list[tuple[str, str, str, float, float]] = [
    ("Truck+Trailer", "Unit 1 — L&P End-Dump", "Primary tractor + lined end-dump", 1.75, 0.85),
    ("Truck+Trailer", "Unit 2 — Backup tractor + trailer", "Secondary revenue unit", 1.65, 0.80),
    ("Trailer", "Trailer A — 39ft Frameless End-Dump", "24-ton lined", 1.50, 0.75),
    ("Trailer", "Trailer B — 39ft End-Dump", "Spare / swing", 1.45, 0.70),
    ("Driver", "Phillip Vencill", "Owner-operator · primary", 0.0, 0.0),
    ("Driver", "Lawson", "Co-owner / relief driver", 0.0, 0.0),
]


def ensure_fleet_columns(conn) -> None:
    """Ensure assets has optional driver linkage and loads has asset/driver fields."""
    asset_cols = {row[1] for row in conn.execute("PRAGMA table_info(assets)").fetchall()}
    if asset_cols:
        if "driver_name" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN driver_name TEXT")
        if "plate" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN plate TEXT")
        if "notes" not in asset_cols:
            # description already exists; notes optional
            pass
    load_cols = {row[1] for row in conn.execute("PRAGMA table_info(loads)").fetchall()}
    if load_cols:
        if "asset_id" not in load_cols:
            conn.execute("ALTER TABLE loads ADD COLUMN asset_id INTEGER")
        if "driver_name" not in load_cols:
            conn.execute("ALTER TABLE loads ADD COLUMN driver_name TEXT")
        if "trailer_name" not in load_cols:
            conn.execute("ALTER TABLE loads ADD COLUMN trailer_name TEXT")


def seed_fleet_if_empty(conn) -> int:
    ensure_fleet_columns(conn)
    count = conn.execute("SELECT COUNT(*) AS c FROM assets").fetchone()[0]
    if count and count > 0:
        # Ensure at least one Driver asset exists for multi-driver view
        drivers = conn.execute(
            "SELECT COUNT(*) FROM assets WHERE lower(asset_type) = 'driver'"
        ).fetchone()[0]
        if drivers == 0:
            for a in FLEET_SEED:
                if a[0] == "Driver":
                    conn.execute(
                        """
                        INSERT INTO assets
                            (asset_type, name, description, loaded_rate_per_mile, empty_rate_per_mile, driver_name)
                        VALUES (?,?,?,?,?,?)
                        """,
                        (a[0], a[1], a[2], a[3], a[4], a[1]),
                    )
            return 2
        return 0
    for a in FLEET_SEED:
        driver_name = a[1] if a[0] == "Driver" else None
        conn.execute(
            """
            INSERT INTO assets
                (asset_type, name, description, loaded_rate_per_mile, empty_rate_per_mile, driver_name)
            VALUES (?,?,?,?,?,?)
            """,
            (a[0], a[1], a[2], a[3], a[4], driver_name),
        )
    return len(FLEET_SEED)


def fetch_assets(conn=None) -> pd.DataFrame:
    owns = conn is None
    if owns:
        conn = get_conn()
    try:
        ensure_fleet_columns(conn)
        seed_fleet_if_empty(conn)
        if owns:
            conn.commit()
        return pd.read_sql_query(
            "SELECT * FROM assets WHERE status IS NULL OR status = 'Active' ORDER BY asset_type, name",
            conn,
        )
    except Exception:
        return pd.DataFrame()
    finally:
        if owns:
            conn.close()


def fetch_active_loads_by_asset(conn=None) -> pd.DataFrame:
    owns = conn is None
    if owns:
        conn = get_conn()
    try:
        ensure_fleet_columns(conn)
        return pd.read_sql_query(
            """
            SELECT id, bol_number, shipper, commodity, origin, destination,
                   status, asset_id, driver_name, trailer_name, weight_tons,
                   total_revenue, pickup_date
            FROM loads
            WHERE lower(COALESCE(status, '')) NOT IN ('completed', 'delivered', 'paid', 'cancelled', 'canceled')
            ORDER BY pickup_date DESC, id DESC
            """,
            conn,
        )
    except Exception:
        return pd.DataFrame()
    finally:
        if owns:
            conn.close()


def assign_load_to_unit(
    load_id: int,
    *,
    asset_id: int | None = None,
    driver_name: str = "",
    trailer_name: str = "",
    conn=None,
) -> None:
    owns = conn is None
    if owns:
        conn = get_conn()
    try:
        ensure_fleet_columns(conn)
        conn.execute(
            """
            UPDATE loads
            SET asset_id = ?, driver_name = ?, trailer_name = ?
            WHERE id = ?
            """,
            (asset_id, driver_name or None, trailer_name or None, load_id),
        )
        if owns:
            conn.commit()
    finally:
        if owns:
            conn.close()


def build_fleet_board(
    assets_df: pd.DataFrame,
    loads_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """One card per truck/trailer/driver with current assignment summary."""
    cards: list[dict[str, Any]] = []
    if assets_df is None or assets_df.empty:
        return cards

    active = loads_df if loads_df is not None else pd.DataFrame()

    for _, asset in assets_df.iterrows():
        aid = asset.get("id")
        atype = str(asset.get("asset_type") or "Unit")
        name = str(asset.get("name") or "—")
        assigned = pd.DataFrame()
        if not active.empty:
            if atype.lower() == "driver":
                dname = str(asset.get("driver_name") or name)
                mask = active["driver_name"].fillna("").astype(str).str.lower() == dname.lower()
                assigned = active.loc[mask]
            elif "asset_id" in active.columns and pd.notna(aid):
                assigned = active.loc[active["asset_id"] == aid]
                if assigned.empty and atype.lower() == "trailer":
                    tmask = active["trailer_name"].fillna("").astype(str).str.lower() == name.lower()
                    assigned = active.loc[tmask]

        load_summary = "Available"
        bol = ""
        status = "Available"
        if not assigned.empty:
            row = assigned.iloc[0]
            bol = str(row.get("bol_number") or "")
            status = str(row.get("status") or "Assigned")
            load_summary = (
                f"{row.get('commodity', 'Load')} · "
                f"{row.get('origin', '?')} → {row.get('destination', '?')}"
            )

        cards.append(
            {
                "id": aid,
                "asset_type": atype,
                "name": name,
                "description": str(asset.get("description") or ""),
                "driver_name": str(asset.get("driver_name") or ""),
                "status": status,
                "load_summary": load_summary,
                "bol_number": bol,
                "active_loads": len(assigned),
            }
        )
    return cards


def render_fleet_page(
    *,
    fetch_loads: Callable[[], pd.DataFrame] | None = None,
    render_page_header: Callable[[str, str], None] | None = None,
    clear_cache: Callable[[], None] | None = None,
    log_audit: Callable[..., Any] | None = None,
) -> None:
    """Full multi-trailer / multi-driver UI for Streamlit."""
    if render_page_header:
        render_page_header("Fleet", "Multi-trailer · multi-driver assignment board")
    else:
        st.subheader("Fleet — Multi-trailer / Driver view")
        st.caption("Assign loads across trucks, trailers, and drivers.")

    with closing(get_conn()) as conn:
        ensure_fleet_columns(conn)
        n = seed_fleet_if_empty(conn)
        conn.commit()
        assets_df = fetch_assets(conn)
        active_loads = fetch_active_loads_by_asset(conn)

    if n and n > 0:
        st.info(f"Seeded {n} fleet unit(s) / driver(s).")

    cards = build_fleet_board(assets_df, active_loads)

    # Filters
    f1, f2 = st.columns(2)
    type_opts = ["All"] + sorted(
        {str(c["asset_type"]) for c in cards if c.get("asset_type")}
    )
    type_filter = f1.selectbox("Asset type", type_opts, key="fleet_type_filter")
    status_filter = f2.selectbox(
        "Status",
        ["All", "Available", "Assigned"],
        key="fleet_status_filter",
    )

    filtered = cards
    if type_filter != "All":
        filtered = [c for c in filtered if c["asset_type"] == type_filter]
    if status_filter == "Available":
        filtered = [c for c in filtered if c["active_loads"] == 0]
    elif status_filter == "Assigned":
        filtered = [c for c in filtered if c["active_loads"] > 0]

    # KPI row
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Units", len([c for c in cards if c["asset_type"] != "Driver"]))
    k2.metric("Drivers", len([c for c in cards if c["asset_type"] == "Driver"]))
    k3.metric("On load", len([c for c in cards if c["active_loads"] > 0]))
    k4.metric("Available", len([c for c in cards if c["active_loads"] == 0]))

    st.markdown("### Board")
    if not filtered:
        st.info("No fleet units match filters.")
    else:
        cols = st.columns(2)
        for i, card in enumerate(filtered):
            with cols[i % 2]:
                badge = "🟢" if card["active_loads"] == 0 else "🟠"
                st.markdown(
                    f"""
                    <div class="lf-panel" style="margin-bottom:0.65rem;padding:0.85rem 1rem;">
                        <strong>{badge} {card['name']}</strong>
                        <span style="color:var(--lf-muted);font-size:0.85rem;"> · {card['asset_type']}</span><br/>
                        <span style="font-size:0.9rem;">{card['load_summary']}</span><br/>
                        <span style="font-size:0.8rem;color:var(--lf-muted);">
                            Status: {card['status']}
                            {(' · BOL ' + card['bol_number']) if card['bol_number'] else ''}
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("### Assign load → unit / driver")
    all_loads = fetch_loads() if fetch_loads else pd.DataFrame()
    if all_loads is None or all_loads.empty:
        st.caption("Log loads in Logger, then assign them here.")
        return

    open_mask = ~all_loads["status"].fillna("").astype(str).str.lower().isin(
        ["completed", "delivered", "paid", "cancelled", "canceled"]
    )
    open_loads = all_loads.loc[open_mask] if not all_loads.empty else all_loads
    if open_loads.empty:
        open_loads = all_loads.head(20)

    load_labels = {
        f"{r.get('bol_number', r.get('id'))} — {r.get('shipper', '?')} ({r.get('status', '')})": int(r["id"])
        for _, r in open_loads.iterrows()
        if "id" in r and pd.notna(r["id"])
    }
    if not load_labels:
        st.warning("No loads with IDs available for assignment.")
        return

    drivers = (
        assets_df.loc[assets_df["asset_type"].astype(str).str.lower() == "driver", "name"]
        .astype(str)
        .tolist()
        if not assets_df.empty
        else []
    )
    trailers = (
        assets_df.loc[
            assets_df["asset_type"].astype(str).str.lower().isin(["trailer", "truck+trailer"]),
            "name",
        ]
        .astype(str)
        .tolist()
        if not assets_df.empty
        else []
    )
    units = (
        assets_df.loc[
            assets_df["asset_type"].astype(str).str.lower().isin(["truck+trailer", "truck"]),
            ["id", "name"],
        ]
        if not assets_df.empty
        else pd.DataFrame(columns=["id", "name"])
    )

    a1, a2, a3 = st.columns(3)
    pick_load = a1.selectbox("Load", list(load_labels.keys()), key="fleet_assign_load")
    pick_driver = a2.selectbox("Driver", ["—"] + drivers, key="fleet_assign_driver")
    pick_trailer = a3.selectbox("Trailer / unit", ["—"] + trailers, key="fleet_assign_trailer")

    unit_id = None
    if not units.empty and pick_trailer != "—":
        match = units.loc[units["name"] == pick_trailer]
        if not match.empty:
            unit_id = int(match.iloc[0]["id"])
        else:
            # try trailer-only assets
            tmatch = assets_df.loc[assets_df["name"] == pick_trailer]
            if not tmatch.empty:
                unit_id = int(tmatch.iloc[0]["id"])

    if st.button("Assign", type="primary", use_container_width=True, key="fleet_assign_btn"):
        lid = load_labels[pick_load]
        try:
            assign_load_to_unit(
                lid,
                asset_id=unit_id,
                driver_name="" if pick_driver == "—" else pick_driver,
                trailer_name="" if pick_trailer == "—" else pick_trailer,
            )
            if log_audit:
                log_audit(
                    "load_assigned",
                    entity_type="load",
                    entity_id=lid,
                    detail=f"driver={pick_driver} trailer={pick_trailer} asset_id={unit_id}",
                    actor="dispatch",
                )
            if clear_cache:
                clear_cache()
            st.success(f"Assigned load {pick_load}")
            st.rerun()
        except Exception as exc:
            st.error(f"Assignment failed: {exc}")

    with st.expander("Add fleet unit / driver"):
        with st.form("fleet_add_asset"):
            t = st.selectbox("Type", ["Driver", "Trailer", "Truck+Trailer", "Truck"])
            name = st.text_input("Name", placeholder="Unit 3 or Driver name")
            desc = st.text_input("Description", placeholder="Optional notes")
            if st.form_submit_button("Add", use_container_width=True):
                if not name.strip():
                    st.error("Name required.")
                else:
                    with closing(get_conn()) as conn:
                        ensure_fleet_columns(conn)
                        conn.execute(
                            """
                            INSERT INTO assets
                                (asset_type, name, description, loaded_rate_per_mile,
                                 empty_rate_per_mile, driver_name, status)
                            VALUES (?,?,?,?,?,?,?)
                            """,
                            (
                                t,
                                name.strip(),
                                desc.strip(),
                                1.5 if t != "Driver" else 0.0,
                                0.75 if t != "Driver" else 0.0,
                                name.strip() if t == "Driver" else None,
                                "Active",
                            ),
                        )
                        conn.commit()
                    if log_audit:
                        log_audit(
                            "asset_created",
                            entity_type="asset",
                            detail=f"{t}: {name.strip()}",
                            actor="dispatch",
                        )
                    if clear_cache:
                        clear_cache()
                    st.success(f"Added {t}: {name}")
                    st.rerun()
