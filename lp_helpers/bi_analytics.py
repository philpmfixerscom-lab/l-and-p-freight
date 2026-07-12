"""
Analytics & BI Dashboard — trend KPIs replacing the snapshot.
Provides margin by lane, deadhead %, asset utilization, weekly revenue.
Renders in the Analytics screen of the app.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lp_helpers.database import get_conn, fetch_loads, fetch_assets


# ===========================================================================
# Data queries
# ===========================================================================

def _loads_with_assets() -> pd.DataFrame:
    """Loads joined with asset info for utilization analysis."""
    conn = get_conn()
    df = pd.read_sql(
        """
        SELECT l.*, a.name as asset_name, a.asset_type, a.loaded_rate_per_mile, a.empty_rate_per_mile
        FROM loads l
        LEFT JOIN assets a ON l.asset_id = a.id
        ORDER BY l.pickup_date DESC, l.id DESC
        """,
        conn,
    )
    conn.close()
    return df


def _settlements_margin() -> pd.DataFrame:
    """Settlements with revenue from linked loads for margin calculation."""
    conn = get_conn()
    df = pd.read_sql(
        """
        SELECT s.*, l.total_revenue, l.shipper, l.commodity, l.loaded_miles, l.deadhead_miles,
               l.pickup_date, l.bol_number, a.name as asset_name
        FROM settlements s
        LEFT JOIN loads l ON s.load_id = l.id
        LEFT JOIN assets a ON s.asset_id = a.id
        ORDER BY s.created_at DESC
        """,
        conn,
    )
    conn.close()
    return df


# ===========================================================================
# KPI computations
# ===========================================================================

def compute_trend_kpis(df: pd.DataFrame) -> dict[str, Any]:
    """
    Compute all trend KPIs from a filtered loads DataFrame.
    Returns dict with margin_by_lane, deadhead_pct, asset_utilization, weekly_revenue, etc.
    """
    result: dict[str, Any] = {
        "margin_by_lane": {},
        "deadhead_pct": 0.0,
        "asset_utilization": {},
        "weekly_revenue": {},
        "total_revenue": 0.0,
        "total_margin": 0.0,
        "load_count": 0,
        "avg_rate_per_ton": 0.0,
        "revenue_per_loaded_mile": 0.0,
    }

    if df.empty:
        return result

    df = df.copy()
    df["pickup_date"] = pd.to_datetime(df["pickup_date"], errors="coerce")
    df["loaded_miles"] = pd.to_numeric(df["loaded_miles"], errors="coerce").fillna(0)
    df["deadhead_miles"] = pd.to_numeric(df["deadhead_miles"], errors="coerce").fillna(0)
    df["total_revenue"] = pd.to_numeric(df["total_revenue"], errors="coerce").fillna(0)
    df["weight_tons"] = pd.to_numeric(df["weight_tons"], errors="coerce").fillna(0)
    df["rate_per_ton"] = pd.to_numeric(df["rate_per_ton"], errors="coerce").fillna(0)

    total_loads = len(df)
    result["load_count"] = total_loads
    result["total_revenue"] = float(df["total_revenue"].sum())

    # Average rate per ton
    result["avg_rate_per_ton"] = float(df["rate_per_ton"].mean()) if total_loads > 0 else 0.0

    # Revenue per loaded mile
    total_loaded = df["loaded_miles"].sum()
    result["revenue_per_loaded_mile"] = float(result["total_revenue"] / total_loaded) if total_loaded > 0 else 0.0

    # Deadhead %
    total_miles = df["loaded_miles"].sum() + df["deadhead_miles"].sum()
    result["deadhead_pct"] = round(float(df["deadhead_miles"].sum() / total_miles * 100), 1) if total_miles > 0 else 0.0

    # Margin by lane (approximate margin = revenue - est_driver_cost)
    # Use average loaded/empty rates from assets if available, else defaults
    result["margin_by_lane"] = _compute_margin_by_lane(df)

    # Asset utilization
    result["asset_utilization"] = _compute_asset_utilization(df)

    # Weekly revenue trend
    result["weekly_revenue"] = _compute_weekly_revenue(df)

    return result


def _compute_margin_by_lane(df: pd.DataFrame) -> dict[str, Any]:
    """Compute margin per unique lane (origin → destination)."""
    if df.empty:
        return {}

    df["lane"] = df["origin"].fillna("?").astype(str) + " → " + df["destination"].fillna("?").astype(str)
    lane_groups = df.groupby("lane")

    margins = {}
    for lane, group in lane_groups:
        revenue = float(group["total_revenue"].sum())
        loaded = float(group["loaded_miles"].sum())
        deadhead = float(group["deadhead_miles"].sum())
        # Estimate driver cost: loaded $1.75/mi + deadhead $0.85/mi (defaults)
        est_driver_cost = (loaded * 1.75) + (deadhead * 0.85)
        margin = revenue - est_driver_cost
        margin_pct = round((margin / revenue * 100), 1) if revenue > 0 else 0.0
        load_count = len(group)
        margins[lane] = {
            "revenue": round(revenue, 2),
            "est_driver_cost": round(est_driver_cost, 2),
            "margin": round(margin, 2),
            "margin_pct": margin_pct,
            "loads": load_count,
            "loaded_miles": round(loaded, 0),
            "deadhead_miles": round(deadhead, 0),
            "deadhead_pct": round((deadhead / (loaded + deadhead) * 100), 1) if (loaded + deadhead) > 0 else 0,
        }
    return margins


def _compute_asset_utilization(df: pd.DataFrame) -> dict[str, Any]:
    """Compute utilization metrics per asset (truck/trailer)."""
    if df.empty or "asset_name" not in df.columns:
        return {}

    util = {}
    for _, row in df.iterrows():
        asset = str(row.get("asset_name", "Unassigned"))
        if asset not in util:
            util[asset] = {
                "loads": 0,
                "total_miles": 0.0,
                "loaded_miles": 0.0,
                "deadhead_miles": 0.0,
                "total_revenue": 0.0,
            }
        util[asset]["loads"] += 1
        loaded = float(row.get("loaded_miles", 0))
        deadhead = float(row.get("deadhead_miles", 0))
        util[asset]["loaded_miles"] += loaded
        util[asset]["deadhead_miles"] += deadhead
        util[asset]["total_miles"] += loaded + deadhead
        util[asset]["total_revenue"] += float(row.get("total_revenue", 0))

    for asset, data in util.items():
        total = data["total_miles"]
        data["loaded_share_pct"] = round((data["loaded_miles"] / total * 100), 1) if total > 0 else 0.0
        data["deadhead_share_pct"] = round((data["deadhead_miles"] / total * 100), 1) if total > 0 else 0.0
        data["revenue_per_mile"] = round(data["total_revenue"] / data["loaded_miles"], 2) if data["loaded_miles"] > 0 else 0.0

    return util


def _compute_weekly_revenue(df: pd.DataFrame) -> dict[str, Any]:
    """Compute weekly revenue totals for trend charts."""
    if df.empty:
        return {}

    df = df.dropna(subset=["pickup_date"])
    if df.empty:
        return {}

    df["week"] = df["pickup_date"].dt.isocalendar().week.astype(int)
    df["year"] = df["pickup_date"].dt.isocalendar().year.astype(int)
    df["week_label"] = df["year"].astype(str) + "-W" + df["week"].astype(str).str.zfill(2)

    weekly = df.groupby("week_label").agg(
        revenue=("total_revenue", "sum"),
        loads=("id", "count"),
        loaded_miles=("loaded_miles", "sum"),
        deadhead_miles=("deadhead_miles", "sum"),
    ).reset_index()

    weekly["deadhead_pct"] = round(
        weekly["deadhead_miles"] / (weekly["loaded_miles"] + weekly["deadhead_miles"]) * 100, 1
    )

    result = {}
    for _, row in weekly.iterrows():
        result[str(row["week_label"])] = {
            "revenue": round(float(row["revenue"]), 2),
            "loads": int(row["loads"]),
            "loaded_miles": round(float(row["loaded_miles"]), 0),
            "deadhead_miles": round(float(row["deadhead_miles"]), 0),
            "deadhead_pct": float(row["deadhead_pct"]),
        }

    return result


# ===========================================================================
# Chart builders
# ===========================================================================

def build_margin_by_lane_chart(margins: dict[str, Any]) -> go.Figure | None:
    """Horizontal bar chart of margin by lane."""
    if not margins:
        return None
    lanes = list(margins.keys())
    margin_vals = [m["margin"] for m in margins.values()]
    rev_vals = [m["revenue"] for m in margins.values()]
    load_counts = [m["loads"] for m in margins.values()]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=lanes,
        x=margin_vals,
        name="Margin ($)",
        orientation="h",
        marker_color="#16a34a",
        text=[f"${v:,.0f}" for v in margin_vals],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        y=lanes,
        x=rev_vals,
        name="Revenue ($)",
        orientation="h",
        marker_color="#2563eb",
        opacity=0.5,
        text=[f"${v:,.0f}" for v in rev_vals],
        textposition="outside",
    ))
    fig.update_layout(
        title="Margin & Revenue by Lane",
        barmode="group",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )
    return fig


def build_deadhead_trend_chart(weekly: dict[str, Any]) -> go.Figure | None:
    """Line chart showing deadhead % trend over weeks."""
    if not weekly:
        return None
    weeks = sorted(weekly.keys())
    dh_pcts = [weekly[w]["deadhead_pct"] for w in weeks]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=weeks,
        y=dh_pcts,
        mode="lines+markers",
        name="Deadhead %",
        line=dict(color="#ea580c", width=3),
        marker=dict(size=8, color="#ea580c"),
        fill="tozeroy",
        fillcolor="rgba(234,88,12,0.12)",
    ))
    fig.add_hline(y=20, line_dash="dash", line_color="#dc2626", annotation_text="Target 20%")
    fig.update_layout(
        title="Deadhead % Trend (Weekly)",
        yaxis_title="Deadhead %",
        yaxis=dict(range=[0, 100]),
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )
    return fig


def build_weekly_revenue_chart(weekly: dict[str, Any]) -> go.Figure | None:
    """Bar chart of weekly revenue."""
    if not weekly:
        return None
    weeks = sorted(weekly.keys())
    revenues = [weekly[w]["revenue"] for w in weeks]
    loads = [weekly[w]["loads"] for w in weeks]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=weeks,
        y=revenues,
        name="Revenue",
        marker_color="#2563eb",
        text=[f"${v:,.0f}" for v in revenues],
        textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        x=weeks,
        y=[l * max(revenues) / max(loads) * 0.4 if max(loads) > 0 else 0 for l in loads],
        name="Load Count (scaled)",
        yaxis="y2",
        line=dict(color="#16a34a", width=2, dash="dot"),
        marker=dict(symbol="diamond", size=6),
    ))
    fig.update_layout(
        title="Weekly Revenue",
        yaxis_title="Revenue ($)",
        yaxis2=dict(
            title="Loads",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )
    return fig


def build_asset_utilization_chart(util: dict[str, Any]) -> go.Figure | None:
    """Stacked bar of loaded vs deadhead miles per asset."""
    if not util:
        return None
    assets = list(util.keys())
    loaded = [util[a]["loaded_miles"] for a in assets]
    deadhead = [util[a]["deadhead_miles"] for a in assets]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=assets,
        y=loaded,
        name="Loaded Miles",
        marker_color="#16a34a",
        text=[f"{v:,.0f}" for v in loaded],
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        x=assets,
        y=deadhead,
        name="Deadhead Miles",
        marker_color="#ea580c",
        text=[f"{v:,.0f}" for v in deadhead],
        textposition="inside",
    ))
    fig.update_layout(
        title="Asset Utilization (Miles)",
        barmode="stack",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )
    return fig


def build_margin_pct_chart(margins: dict[str, Any]) -> go.Figure | None:
    """Horizontal bar chart of margin % by lane."""
    if not margins:
        return None
    lanes = list(margins.keys())
    margin_pcts = [m["margin_pct"] for m in margins.values()]

    colors = ["#16a34a" if p >= 15 else "#ea580c" if p >= 5 else "#dc2626" for p in margin_pcts]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=lanes,
        x=margin_pcts,
        orientation="h",
        marker_color=colors,
        text=[f"{v}%" for v in margin_pcts],
        textposition="outside",
    ))
    fig.add_vline(x=15, line_dash="dash", line_color="#16a34a", annotation_text="Target 15%")
    fig.update_layout(
        title="Margin % by Lane",
        xaxis_title="Margin %",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )
    return fig


# ===========================================================================
# Main render function
# ===========================================================================

def render_bi_analytics_page() -> None:
    """Render the full Analytics & BI Dashboard replacing the old snapshot."""
    st.markdown('<div class="lf-page-title">📊 Analytics & BI</div>', unsafe_allow_html=True)
    st.caption("Trend KPIs — margin by lane, deadhead %, asset utilization, weekly revenue")

    # Date range filter
    f1, f2 = st.columns(2)
    with f1:
        start_date = st.date_input("From", value=date.today() - timedelta(days=90), key="bi_start")
    with f2:
        end_date = st.date_input("To", value=date.today(), key="bi_end")

    loads_df = _loads_with_assets()

    # Filter by date
    if not loads_df.empty:
        loads_df["pickup_date_dt"] = pd.to_datetime(loads_df["pickup_date"], errors="coerce")
        mask = (loads_df["pickup_date_dt"] >= pd.Timestamp(start_date)) & \
               (loads_df["pickup_date_dt"] <= pd.Timestamp(end_date))
        loads_df = loads_df[mask]

    kpis = compute_trend_kpis(loads_df)

    # --- KPI Cards ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Revenue", f"${kpis['total_revenue']:,.0f}")
    k2.metric("Loads", f"{kpis['load_count']}")
    k3.metric("Deadhead %", f"{kpis['deadhead_pct']}%", delta=f"{kpis['deadhead_pct'] - 20:.1f}%" if kpis['deadhead_pct'] else None,
              delta_color="inverse")
    k4.metric("Avg $/Ton", f"${kpis['avg_rate_per_ton']:.2f}")

    k5, k6 = st.columns(2)
    k5.metric("Revenue per Loaded Mile", f"${kpis['revenue_per_loaded_mile']:.2f}")
    total_margin = sum(m["margin"] for m in kpis.get("margin_by_lane", {}).values())
    k6.metric("Est. Total Margin", f"${total_margin:,.0f}")

    if loads_df.empty:
        st.info("No loads match the selected date range. Log loads or expand the date range.")
        return

    # --- Charts ---
    tab1, tab2, tab3, tab4 = st.tabs(["💰 Margin by Lane", "📉 Deadhead Trend", "📈 Weekly Revenue", "🚛 Asset Utilization"])

    with tab1:
        margins = kpis.get("margin_by_lane", {})
        if margins:
            fig_margin = build_margin_by_lane_chart(margins)
            if fig_margin:
                st.plotly_chart(fig_margin, use_container_width=True)
            fig_margin_pct = build_margin_pct_chart(margins)
            if fig_margin_pct:
                st.plotly_chart(fig_margin_pct, use_container_width=True)

            # Detail table
            st.markdown("##### Margin Detail by Lane")
            detail_rows = []
            for lane, m in margins.items():
                detail_rows.append({
                    "Lane": lane,
                    "Revenue": f"${m['revenue']:,.0f}",
                    "Est. Driver Cost": f"${m['est_driver_cost']:,.0f}",
                    "Margin": f"${m['margin']:,.0f}",
                    "Margin %": f"{m['margin_pct']}%",
                    "Loads": m['loads'],
                    "Loaded Mi": f"{m['loaded_miles']:,.0f}",
                    "Deadhead Mi": f"{m['deadhead_miles']:,.0f}",
                    "DH %": f"{m['deadhead_pct']}%",
                })
            if detail_rows:
                st.dataframe(detail_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No lane data available. Log loads with origin/destination to see margin by lane.")

    with tab2:
        weekly = kpis.get("weekly_revenue", {})
        fig_dh = build_deadhead_trend_chart(weekly)
        if fig_dh:
            st.plotly_chart(fig_dh, use_container_width=True)
        else:
            st.info("Not enough data for deadhead trend.")

        st.metric("Overall Deadhead %", f"{kpis['deadhead_pct']}%")
        if kpis['deadhead_pct'] > 20:
            st.warning("Deadhead exceeds 20% target. Focus on backhaul loads via Trimac or load board.")
        elif kpis['deadhead_pct'] < 10:
            st.success("Excellent deadhead management — under 10%!")

    with tab3:
        fig_wk = build_weekly_revenue_chart(weekly)
        if fig_wk:
            st.plotly_chart(fig_wk, use_container_width=True)
        else:
            st.info("Not enough data for weekly revenue trend.")

        # Weekly detail
        if weekly:
            st.markdown("##### Weekly Revenue Detail")
            wk_rows = []
            for wk in sorted(weekly.keys()):
                w = weekly[wk]
                wk_rows.append({
                    "Week": wk,
                    "Revenue": f"${w['revenue']:,.0f}",
                    "Loads": w['loads'],
                    "Loaded Mi": f"{w['loaded_miles']:,.0f}",
                    "Deadhead Mi": f"{w['deadhead_miles']:,.0f}",
                    "DH %": f"{w['deadhead_pct']}%",
                })
            if wk_rows:
                st.dataframe(wk_rows, use_container_width=True, hide_index=True)

    with tab4:
        util = kpis.get("asset_utilization", {})
        if util:
            fig_util = build_asset_utilization_chart(util)
            if fig_util:
                st.plotly_chart(fig_util, use_container_width=True)

            # Utilization detail
            st.markdown("##### Asset Utilization Detail")
            util_rows = []
            for asset, u in util.items():
                util_rows.append({
                    "Asset": asset,
                    "Loads": u['loads'],
                    "Total Miles": f"{u['total_miles']:,.0f}",
                    "Loaded Mi": f"{u['loaded_miles']:,.0f}",
                    "Deadhead Mi": f"{u['deadhead_miles']:,.0f}",
                    "Loaded %": f"{u['loaded_share_pct']}%",
                    "Rev/Mi": f"${u['revenue_per_mile']:.2f}",
                })
            if util_rows:
                st.dataframe(util_rows, use_container_width=True, hide_index=True)
        else:
            st.info("Assign assets to loads to see utilization metrics.")

    # Settlement margin analysis
    st.markdown("---")
    st.markdown("#### Settlement Margin Analysis")
    sett_df = _settlements_margin()
    if not sett_df.empty:
        sett_df["pickup_date_dt"] = pd.to_datetime(sett_df["pickup_date"], errors="coerce")
        mask = (sett_df["pickup_date_dt"] >= pd.Timestamp(start_date)) & \
               (sett_df["pickup_date_dt"] <= pd.Timestamp(end_date))
        sett_df = sett_df[mask]

        if not sett_df.empty:
            sett_df["actual_margin"] = sett_df["total_revenue"].fillna(0) - sett_df["total_pay"].fillna(0)
            sett_df["actual_margin_pct"] = round(
                sett_df["actual_margin"] / sett_df["total_revenue"].replace(0, pd.NA) * 100, 1
            )

            total_sett_rev = float(sett_df["total_revenue"].sum())
            total_sett_pay = float(sett_df["total_pay"].sum())
            actual_margin = total_sett_rev - total_sett_pay
            margin_pct = round((actual_margin / total_sett_rev * 100), 1) if total_sett_rev > 0 else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("Settlement Revenue", f"${total_sett_rev:,.0f}")
            c2.metric("Driver Pay", f"${total_sett_pay:,.0f}")
            c3.metric("Actual Margin", f"${actual_margin:,.0f} ({margin_pct}%)")

            # Per-load margin
            st.dataframe(
                sett_df[["bol_number", "shipper", "commodity", "total_revenue", "total_pay", "actual_margin", "actual_margin_pct"]]
                .rename(columns={
                    "total_revenue": "Revenue", "total_pay": "Driver Pay",
                    "actual_margin": "Margin", "actual_margin_pct": "Margin %",
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No settlements in date range.")
    else:
        st.info("No settlements yet. Create settlements in Billing & Pay to see margin analysis.")