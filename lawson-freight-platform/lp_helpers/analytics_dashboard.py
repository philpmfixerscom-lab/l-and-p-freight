"""Analytics tab — Plotly charts, KPIs, filters for L & P Freight Platform."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def filter_loads_df(
    loads_df: pd.DataFrame,
    start_date: date | None,
    end_date: date | None,
    commodity: str | None,
) -> pd.DataFrame:
    if loads_df.empty:
        return loads_df
    df = loads_df.copy()
    df["pickup_date"] = pd.to_datetime(df["pickup_date"], errors="coerce")
    if start_date:
        df = df[df["pickup_date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["pickup_date"] <= pd.Timestamp(end_date)]
    if commodity and commodity != "All":
        df = df[df["commodity"] == commodity]
    return df


def compute_analytics_kpis(df: pd.DataFrame) -> dict[str, Any]:
    empty = {
        "total_revenue": 0.0,
        "avg_per_mile": 0.0,
        "loads_completed": 0,
        "top_shipper": "—",
        "loaded_share": 0.0,
        "deadhead_miles": 0.0,
    }
    if df.empty:
        return empty

    revenue = df["total_revenue"].fillna(0).sum()
    loaded = df["loaded_miles"].fillna(df["miles"]).fillna(0).sum()
    total_miles = df["miles"].fillna(0).sum()
    deadhead = df["deadhead_miles"].fillna(0).sum()
    if deadhead <= 0 and total_miles > 0:
        deadhead = max(0.0, total_miles - loaded)

    completed = df[df["status"].astype(str).str.lower().isin(["completed", "delivered", "paid"])]
    loads_done = len(completed) if not completed.empty else len(df)

    top_shipper = "—"
    if "shipper" in df.columns and not df["shipper"].dropna().empty:
        top_shipper = (
            df.groupby("shipper")["total_revenue"].sum().idxmax()
        )

    return {
        "total_revenue": float(revenue),
        "avg_per_mile": float(revenue / loaded) if loaded else 0.0,
        "loads_completed": loads_done,
        "top_shipper": top_shipper,
        "loaded_share": float(loaded / total_miles) if total_miles else 0.0,
        "deadhead_miles": float(deadhead),
    }


def _safe_fig(fig: go.Figure, empty_msg: str) -> go.Figure | None:
    if fig.data:
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e2e8f0"),
            margin=dict(l=20, r=20, t=40, b=20),
            height=320,
        )
        return fig
    return None


def build_revenue_chart(df: pd.DataFrame) -> go.Figure | None:
    if df.empty:
        return None
    chart_df = df.copy()
    chart_df["pickup_date"] = pd.to_datetime(chart_df["pickup_date"], errors="coerce")
    trend = (
        chart_df.dropna(subset=["pickup_date"])
        .groupby(chart_df["pickup_date"].dt.date)["total_revenue"]
        .sum()
        .reset_index()
    )
    trend.columns = ["date", "revenue"]
    if trend.empty:
        return None
    fig = px.area(trend, x="date", y="revenue", title="Revenue Over Time")
    fig.update_traces(line_color="#e85d04", fillcolor="rgba(232,93,4,0.25)")
    return _safe_fig(fig, "No revenue data")


def build_rate_per_mile_chart(df: pd.DataFrame) -> go.Figure | None:
    if df.empty:
        return None
    chart_df = df.copy()
    chart_df["loaded_miles"] = chart_df["loaded_miles"].fillna(chart_df["miles"]).fillna(0)
    chart_df = chart_df[chart_df["loaded_miles"] > 0]
    if chart_df.empty:
        return None
    chart_df["rate_per_mile"] = chart_df["total_revenue"].fillna(0) / chart_df["loaded_miles"]
    chart_df["lane_key"] = (
        chart_df["origin"].fillna("?") + " → " + chart_df["destination"].fillna("?")
    )
    agg = (
        chart_df.groupby(["lane_key", "commodity"], as_index=False)["rate_per_mile"]
        .mean()
        .sort_values("rate_per_mile", ascending=True)
    )
    if agg.empty:
        return None
    fig = px.bar(
        agg,
        x="rate_per_mile",
        y="lane_key",
        color="commodity",
        orientation="h",
        title="Avg $/Mile by Lane & Commodity",
        labels={"rate_per_mile": "$/loaded mi", "lane_key": "Lane"},
    )
    return _safe_fig(fig, "No rate data")


def build_status_pie(df: pd.DataFrame) -> go.Figure | None:
    if df.empty or "status" not in df.columns:
        return None
    counts = df["status"].fillna("Unknown").value_counts().reset_index()
    counts.columns = ["status", "count"]
    fig = px.pie(counts, names="status", values="count", title="Load Status Mix", hole=0.35)
    fig.update_traces(marker=dict(line=dict(color="#0b1628", width=1)))
    return _safe_fig(fig, "No status data")


def build_deadhead_chart(df: pd.DataFrame) -> go.Figure | None:
    if df.empty:
        return None
    chart_df = df.copy()
    chart_df["pickup_date"] = pd.to_datetime(chart_df["pickup_date"], errors="coerce")
    chart_df["loaded_miles"] = chart_df["loaded_miles"].fillna(chart_df["miles"]).fillna(0)
    chart_df["deadhead_miles"] = chart_df["deadhead_miles"].fillna(0)
    chart_df.loc[chart_df["deadhead_miles"] <= 0, "deadhead_miles"] = (
        chart_df["miles"].fillna(0) - chart_df["loaded_miles"]
    ).clip(lower=0)
    chart_df["loaded_pct"] = (
        chart_df["loaded_miles"] / chart_df["miles"].replace(0, pd.NA) * 100
    ).fillna(0)
    trend = (
        chart_df.dropna(subset=["pickup_date"])
        .sort_values("pickup_date")
        [["pickup_date", "loaded_pct", "deadhead_miles"]]
    )
    if trend.empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=trend["pickup_date"],
        y=trend["loaded_pct"],
        name="Loaded %",
        line=dict(color="#22c55e", width=2),
        fill="tozeroy",
        fillcolor="rgba(34,197,94,0.15)",
    ))
    fig.update_layout(
        title="Deadhead Minimization — Loaded Mile %",
        yaxis_title="Loaded %",
        xaxis_title="Pickup Date",
        yaxis=dict(range=[0, 100]),
    )
    return _safe_fig(fig, "No deadhead data")


def render_analytics_page(
    fetch_loads: Callable[[], pd.DataFrame],
    render_page_header: Callable[[str, str], None],
    commodity_options: list[str],
) -> None:
    """Full Analytics tab UI."""
    render_page_header("Analytics", "Revenue, rates per mile, and deadhead over time")
    loads_df = fetch_loads()

    st.markdown('<div class="lf-section-header">🔍 Filters</div>', unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    with f1:
        start = st.date_input("From", value=date.today().replace(month=1, day=1), key="analytics_start")
    with f2:
        end = st.date_input("To", value=date.today(), key="analytics_end")
    with f3:
        commodities = ["All"] + commodity_options
        commodity_filter = st.selectbox("Commodity", commodities, key="analytics_commodity")

    filtered = filter_loads_df(loads_df, start, end, commodity_filter)
    kpis = compute_analytics_kpis(filtered)

    st.markdown('<div class="lf-section-header">📊 KPI Cards</div>', unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Revenue", f"${kpis['total_revenue']:,.0f}")
    k2.metric("Avg $/Mile", f"${kpis['avg_per_mile']:.2f}")
    k3.metric("Loads Completed", f"{kpis['loads_completed']}")
    k4.metric("Top Shipper", str(kpis["top_shipper"])[:18])

    d1, d2 = st.columns(2)
    d1.metric("Loaded Mile Share", f"{kpis['loaded_share']:.0%}")
    d2.metric("Deadhead Miles (period)", f"{kpis['deadhead_miles']:,.0f}")

    if filtered.empty:
        st.info("No loads match filters. Log loads in Load Logger or enable Demo Mode.")
        return

    st.markdown('<div class="lf-section-header">📈 Charts</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        rev_fig = build_revenue_chart(filtered)
        if rev_fig:
            st.plotly_chart(rev_fig, use_container_width=True)
        else:
            st.caption("Revenue chart unavailable for current filters.")
    with c2:
        status_fig = build_status_pie(filtered)
        if status_fig:
            st.plotly_chart(status_fig, use_container_width=True)
        else:
            st.caption("Status chart unavailable.")

    c3, c4 = st.columns(2)
    with c3:
        rate_fig = build_rate_per_mile_chart(filtered)
        if rate_fig:
            st.plotly_chart(rate_fig, use_container_width=True)
        else:
            st.caption("Rate/mile chart unavailable.")
    with c4:
        dh_fig = build_deadhead_chart(filtered)
        if dh_fig:
            st.plotly_chart(dh_fig, use_container_width=True)
        else:
            st.caption("Deadhead chart unavailable.")

    with st.expander("Raw filtered data"):
        st.dataframe(filtered, use_container_width=True, hide_index=True)