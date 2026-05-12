"""
Superstore Executive Dashboard — Streamlit app
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Page config
st.set_page_config(
    page_title="Superstore Executive Dashboard",
    page_icon="🏪",
    layout="wide",
)

# Custom CSS
st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        .metric-card {
            background: #F8F9FA;
            border-radius: 8px;
            padding: 16px 20px;
            border-left: 4px solid #185FA5;
        }
        h1, h2, h3 { color: #1A1A1A; }
        .section-header {
            font-size: 1.1rem;
            font-weight: 600;
            color: #185FA5;
            margin-bottom: 12px;
        }
        footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Constants
PROFIT_TIER_COLORS = {
    "Loss": "#E24B4A",
    "Low": "#BA7517",
    "Medium": "#1A5CFF",
    "High": "#1D9E75",
}
CHART_TEMPLATE = "plotly_white"
PRIMARY = "#185FA5"
GREEN = "#1D9E75"
OUTPUT_DIR = Path("output")

STATE_ABBREV: dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}


# Helpers
def format_currency(n: float) -> str:
    return f"${n:,.0f}"


def format_pct(n: float, decimals: int = 1) -> str:
    return f"{n:.{decimals}f}%"


@st.cache_data
def load_data() -> tuple[pd.DataFrame, dict]:
    fact = pd.read_csv(OUTPUT_DIR / "fact_sales.csv", parse_dates=["Order Date", "Ship Date"])
    with open(OUTPUT_DIR / "exec_summary.json") as f:
        summary = json.load(f)
    return fact, summary


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if filters.get("years"):
        mask &= df["order_year"].isin(filters["years"])
    if filters.get("regions"):
        mask &= df["Region"].isin(filters["regions"])
    if filters.get("categories"):
        mask &= df["Category"].isin(filters["categories"])
    if filters.get("segments"):
        mask &= df["Segment"].isin(filters["segments"])
    if filters.get("ship_modes"):
        mask &= df["Ship Mode"].isin(filters["ship_modes"])
    return df[mask].copy()


def region_profit_tier(df: pd.DataFrame) -> dict[str, str]:
    """Assign a profit tier to each region based on its avg margin."""
    region_margin = df.groupby("Region")["margin_pct"].mean()
    tiers = {}
    for region, margin in region_margin.items():
        if margin < 0:
            tiers[region] = "Loss"
        elif margin < 10:
            tiers[region] = "Low"
        elif margin <= 20:
            tiers[region] = "Medium"
        else:
            tiers[region] = "High"
    return tiers


# Data load
if not (OUTPUT_DIR / "fact_sales.csv").exists():
    st.error(
        "Output files not found. Run the ETL pipeline first:\n\n"
        "```\npython src/etl.py --input data/raw/superstore.csv --output output/\n```"
    )
    st.stop()

df_full, exec_summary = load_data()

# Sidebar filters
if "filters_initialised" not in st.session_state:
    st.session_state.years = sorted(df_full["order_year"].unique().tolist())
    st.session_state.regions = df_full["Region"].unique().tolist()
    st.session_state.categories = df_full["Category"].unique().tolist()
    st.session_state.segments = df_full["Segment"].unique().tolist()
    st.session_state.ship_modes = df_full["Ship Mode"].unique().tolist()
    st.session_state.filters_initialised = True

with st.sidebar:
    st.markdown("## Filters")

    selected_years = st.multiselect(
        "Year",
        options=sorted(df_full["order_year"].unique().tolist()),
        default=st.session_state.years,
        key="years",
    )
    selected_regions = st.multiselect(
        "Region",
        options=sorted(df_full["Region"].unique().tolist()),
        default=st.session_state.regions,
        key="regions",
    )
    selected_categories = st.multiselect(
        "Category",
        options=sorted(df_full["Category"].unique().tolist()),
        default=st.session_state.categories,
        key="categories",
    )
    selected_segments = st.multiselect(
        "Segment",
        options=sorted(df_full["Segment"].unique().tolist()),
        default=st.session_state.segments,
        key="segments",
    )
    selected_ship_modes = st.multiselect(
        "Ship Mode",
        options=sorted(df_full["Ship Mode"].unique().tolist()),
        default=st.session_state.ship_modes,
        key="ship_modes",
    )

    if st.button("Reset all filters"):
        st.session_state.years = sorted(df_full["order_year"].unique().tolist())
        st.session_state.regions = df_full["Region"].unique().tolist()
        st.session_state.categories = df_full["Category"].unique().tolist()
        st.session_state.segments = df_full["Segment"].unique().tolist()
        st.session_state.ship_modes = df_full["Ship Mode"].unique().tolist()
        st.rerun()

    st.divider()
    st.caption(f"Dataset: {len(df_full):,} orders · {df_full['Customer ID'].nunique()} customers")

filters = {
    "years": st.session_state.years,
    "regions": st.session_state.regions,
    "categories": st.session_state.categories,
    "segments": st.session_state.segments,
    "ship_modes": st.session_state.ship_modes,
}

df = apply_filters(df_full, filters)

if df.empty:
    st.warning("No data matches your filters. Adjust the sidebar filters to see results.")
    st.stop()

# Dashboard header
st.title("🏪 Superstore Executive Dashboard")
st.caption(
    f"Showing **{len(df):,}** orders · "
    f"{df['order_month'].nunique()} months · "
    f"{', '.join(str(y) for y in sorted(st.session_state.years))}"
)

# SECTION 1 — KPI Header
st.markdown('<p class="section-header">Key Performance Indicators</p>', unsafe_allow_html=True)

# Compute current vs prior year for deltas
current_years = sorted(st.session_state.years)
prior_years = [y - 1 for y in current_years]
df_prior = apply_filters(
    df_full,
    {**filters, "years": prior_years},
)

cur_rev = df["revenue"].sum()
prior_rev = df_prior["revenue"].sum() if not df_prior.empty else 0.0
rev_delta = ((cur_rev - prior_rev) / prior_rev * 100) if prior_rev else None

cur_profit = df["Profit"].sum()
prior_profit = df_prior["Profit"].sum() if not df_prior.empty else 0.0
profit_delta = ((cur_profit - prior_profit) / prior_profit * 100) if prior_profit else None

cur_margin = (df["Profit"].sum() / df["revenue"].sum() * 100) if cur_rev else 0.0
prior_margin = (
    (df_prior["Profit"].sum() / df_prior["revenue"].sum() * 100)
    if (not df_prior.empty and df_prior["revenue"].sum() > 0)
    else None
)
margin_delta = (cur_margin - prior_margin) if prior_margin is not None else None

cur_orders = df["Order ID"].nunique()
prior_orders = df_prior["Order ID"].nunique() if not df_prior.empty else 0
orders_delta = ((cur_orders - prior_orders) / prior_orders * 100) if prior_orders else None

cur_ship = df["ship_days"].mean()
prior_ship = df_prior["ship_days"].mean() if not df_prior.empty else None
ship_delta = (cur_ship - prior_ship) if prior_ship is not None else None

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

with kpi1:
    st.metric(
        "Total Revenue",
        format_currency(cur_rev),
        delta=f"{rev_delta:+.1f}% vs prior yr" if rev_delta is not None else None,
    )
with kpi2:
    st.metric(
        "Total Profit",
        format_currency(cur_profit),
        delta=f"{profit_delta:+.1f}% vs prior yr" if profit_delta is not None else None,
    )
with kpi3:
    st.metric(
        "Avg Margin %",
        format_pct(cur_margin),
        delta=f"{margin_delta:+.1f}pp vs prior yr" if margin_delta is not None else None,
    )
with kpi4:
    st.metric(
        "Total Orders",
        f"{cur_orders:,}",
        delta=f"{orders_delta:+.1f}% vs prior yr" if orders_delta is not None else None,
    )
with kpi5:
    ship_delta_display = (
        f"{ship_delta:+.1f} days vs prior yr" if ship_delta is not None else None
    )
    st.metric(
        "Avg Ship Days",
        f"{cur_ship:.1f}",
        delta=ship_delta_display,
        delta_color="inverse",
    )

# SECTION 2 — Revenue Trend
st.markdown('<p class="section-header">Revenue & Profit Trends</p>', unsafe_allow_html=True)

monthly_agg = (
    df.groupby("order_month")
    .agg(
        total_revenue=("revenue", "sum"),
        total_profit=("Profit", "sum"),
        total_orders=("Order ID", "nunique"),
    )
    .reset_index()
    .sort_values("order_month")
)
monthly_agg["margin_pct"] = monthly_agg["total_profit"] / monthly_agg["total_revenue"] * 100

fig_trend = go.Figure()
fig_trend.add_trace(
    go.Scatter(
        x=monthly_agg["order_month"],
        y=monthly_agg["total_revenue"],
        name="Revenue",
        line=dict(color=PRIMARY, width=2),
        fill="tozeroy",
        fillcolor="rgba(24,95,165,0.08)",
        customdata=monthly_agg[["total_profit", "margin_pct"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Revenue: $%{y:,.0f}<br>"
            "Profit: $%{customdata[0]:,.0f}<br>"
            "Margin: %{customdata[1]:.1f}%<extra></extra>"
        ),
    )
)
fig_trend.add_trace(
    go.Scatter(
        x=monthly_agg["order_month"],
        y=monthly_agg["total_profit"],
        name="Profit",
        line=dict(color=GREEN, width=2, dash="dash"),
        hovertemplate="<b>%{x}</b><br>Profit: $%{y:,.0f}<extra></extra>",
    )
)
fig_trend.update_layout(
    title="Monthly Revenue & Profit Trend",
    xaxis_title="Month",
    yaxis_title="$ Value",
    template=CHART_TEMPLATE,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=360,
    margin=dict(t=50, b=40),
)
st.plotly_chart(fig_trend, use_container_width=True)

col_reg, col_cat, col_seg = st.columns(3)

# Revenue by Region — horizontal bar
region_agg = (
    df.groupby("Region")
    .agg(total_revenue=("revenue", "sum"), avg_margin=("margin_pct", "mean"))
    .reset_index()
    .sort_values("total_revenue", ascending=True)
)
region_tier_map = region_profit_tier(df)
region_agg["tier"] = region_agg["Region"].map(region_tier_map)
region_agg["bar_color"] = region_agg["tier"].map(PROFIT_TIER_COLORS)

with col_reg:
    fig_reg = go.Figure(
        go.Bar(
            x=region_agg["total_revenue"],
            y=region_agg["Region"],
            orientation="h",
            marker_color=region_agg["bar_color"].tolist(),
            customdata=region_agg[["avg_margin", "tier"]].values,
            hovertemplate=(
                "<b>%{y}</b><br>Revenue: $%{x:,.0f}<br>"
                "Avg Margin: %{customdata[0]:.1f}%<br>"
                "Tier: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig_reg.update_layout(
        title="Revenue by Region",
        template=CHART_TEMPLATE,
        height=300,
        margin=dict(t=40, b=20, l=10, r=10),
        xaxis_title="Revenue ($)",
    )
    st.plotly_chart(fig_reg, use_container_width=True)

# Revenue by Category — donut
cat_agg = (
    df.groupby("Category")["revenue"].sum().reset_index().sort_values("revenue", ascending=False)
)
total_rev_m = cur_rev / 1_000_000

with col_cat:
    fig_donut = go.Figure(
        go.Pie(
            labels=cat_agg["Category"],
            values=cat_agg["revenue"],
            hole=0.55,
            textinfo="label+percent",
            marker=dict(colors=[PRIMARY, "#4A90D9", GREEN]),
        )
    )
    fig_donut.add_annotation(
        text=f"Total<br>${total_rev_m:.1f}M",
        x=0.5, y=0.5,
        font=dict(size=14, color="#1A1A1A"),
        showarrow=False,
    )
    fig_donut.update_layout(
        title="Revenue by Category",
        template=CHART_TEMPLATE,
        height=300,
        margin=dict(t=40, b=20, l=10, r=10),
        showlegend=False,
    )
    st.plotly_chart(fig_donut, use_container_width=True)

# Revenue by Segment — bar
seg_agg = df.groupby("Segment")["revenue"].sum().reset_index().sort_values("revenue", ascending=False)

with col_seg:
    fig_seg = px.bar(
        seg_agg,
        x="Segment",
        y="revenue",
        color="Segment",
        color_discrete_sequence=[PRIMARY, GREEN, "#BA7517"],
        labels={"revenue": "Revenue ($)"},
        title="Revenue by Segment",
        template=CHART_TEMPLATE,
    )
    fig_seg.update_layout(
        height=300,
        margin=dict(t=40, b=20, l=10, r=10),
        showlegend=False,
    )
    fig_seg.update_traces(hovertemplate="<b>%{x}</b><br>Revenue: $%{y:,.0f}<extra></extra>")
    st.plotly_chart(fig_seg, use_container_width=True)

# SECTION 3 — Product Deep Dive
st.markdown('<p class="section-header">Product Deep Dive</p>', unsafe_allow_html=True)

subcat_agg = (
    df.groupby(["Category", "Sub-Category"])
    .agg(
        total_revenue=("revenue", "sum"),
        total_profit=("Profit", "sum"),
        total_units=("Quantity", "sum"),
        avg_margin_pct=("margin_pct", "mean"),
    )
    .reset_index()
)

fig_tree = px.treemap(
    subcat_agg,
    path=[px.Constant("All"), "Category", "Sub-Category"],
    values="total_revenue",
    color="avg_margin_pct",
    color_continuous_scale="RdYlGn",
    range_color=[-50, 50],
    custom_data=["total_units", "avg_margin_pct"],
    title="Revenue by Sub-Category — coloured by Profit Margin %",
    template=CHART_TEMPLATE,
)
fig_tree.update_traces(
    hovertemplate=(
        "<b>%{label}</b><br>"
        "Revenue: $%{value:,.0f}<br>"
        "Units: %{customdata[0]:,}<br>"
        "Margin: %{customdata[1]:.1f}%<extra></extra>"
    )
)
fig_tree.update_layout(
    height=420,
    margin=dict(t=50, b=10),
    coloraxis_colorbar=dict(title="Margin %"),
)
st.plotly_chart(fig_tree, use_container_width=True)

col_top10, col_bot10 = st.columns(2)

with col_top10:
    top10_sub = subcat_agg.nlargest(10, "total_revenue").sort_values("total_revenue")
    fig_top = go.Figure(
        go.Bar(
            x=top10_sub["total_revenue"],
            y=top10_sub["Sub-Category"],
            orientation="h",
            marker_color=PRIMARY,
            hovertemplate="<b>%{y}</b><br>Revenue: $%{x:,.0f}<extra></extra>",
        )
    )
    fig_top.update_layout(
        title="Top 10 Sub-Categories by Revenue",
        template=CHART_TEMPLATE,
        height=360,
        margin=dict(t=40, b=20, l=10, r=10),
        xaxis_title="Revenue ($)",
    )
    st.plotly_chart(fig_top, use_container_width=True)

with col_bot10:
    bot10_sub = subcat_agg.nsmallest(10, "avg_margin_pct").sort_values("avg_margin_pct", ascending=False)
    bot10_sub["color"] = bot10_sub["avg_margin_pct"].apply(
        lambda m: "#E24B4A" if m < 0 else "#BA7517"
    )
    fig_bot = go.Figure(
        go.Bar(
            x=bot10_sub["avg_margin_pct"],
            y=bot10_sub["Sub-Category"],
            orientation="h",
            marker_color=bot10_sub["color"].tolist(),
            hovertemplate="<b>%{y}</b><br>Margin: %{x:.1f}%<extra></extra>",
        )
    )
    fig_bot.update_layout(
        title="Bottom 10 Sub-Categories by Profit Margin %",
        template=CHART_TEMPLATE,
        height=360,
        margin=dict(t=40, b=20, l=10, r=10),
        xaxis_title="Avg Margin %",
    )
    st.plotly_chart(fig_bot, use_container_width=True)

# SECTION 4 — Regional Performance
st.markdown('<p class="section-header">Regional Performance</p>', unsafe_allow_html=True)

reg_yr_agg = (
    df.groupby(["order_year", "Region"])
    .agg(total_revenue=("revenue", "sum"))
    .reset_index()
    .sort_values(["order_year", "Region"])
)

fig_reg_yr = px.bar(
    reg_yr_agg,
    x="order_year",
    y="total_revenue",
    color="Region",
    barmode="group",
    labels={"total_revenue": "Revenue ($)", "order_year": "Year"},
    title="Revenue by Region and Year",
    template=CHART_TEMPLATE,
    color_discrete_sequence=[PRIMARY, GREEN, "#BA7517", "#E24B4A"],
)
fig_reg_yr.update_layout(
    height=380,
    margin=dict(t=50, b=20),
    xaxis=dict(tickmode="linear"),
)
fig_reg_yr.update_traces(
    hovertemplate="<b>%{x} — %{fullData.name}</b><br>Revenue: $%{y:,.0f}<extra></extra>"
)
st.plotly_chart(fig_reg_yr, use_container_width=True)

col_map, col_yoy = st.columns(2)

# State-level choropleth
state_agg = (
    df.groupby("State")
    .agg(total_revenue=("revenue", "sum"), avg_margin_pct=("margin_pct", "mean"))
    .reset_index()
)
state_agg["state_abbrev"] = state_agg["State"].map(STATE_ABBREV)

with col_map:
    fig_map = px.choropleth(
        state_agg,
        locations="state_abbrev",
        locationmode="USA-states",
        color="total_revenue",
        scope="usa",
        hover_name="State",
        hover_data={"state_abbrev": False, "total_revenue": ":,.0f", "avg_margin_pct": ":.1f"},
        color_continuous_scale="Blues",
        labels={"total_revenue": "Revenue ($)", "avg_margin_pct": "Margin %"},
        title="Revenue by State",
    )
    fig_map.update_layout(
        template=CHART_TEMPLATE,
        height=360,
        margin=dict(t=50, b=10, l=0, r=0),
        coloraxis_colorbar=dict(title="Revenue ($)"),
    )
    st.plotly_chart(fig_map, use_container_width=True)

# YoY growth table
with col_yoy:
    st.markdown("**YoY Revenue Growth % by Region**")

    reg_pivot = reg_yr_agg.pivot(index="Region", columns="order_year", values="total_revenue")
    yoy_table = pd.DataFrame(index=reg_pivot.index)
    years_sorted = sorted(reg_pivot.columns)
    for i in range(1, len(years_sorted)):
        yr = years_sorted[i]
        prev_yr = years_sorted[i - 1]
        if prev_yr in reg_pivot.columns:
            yoy_table[f"{prev_yr}→{yr}"] = (
                (reg_pivot[yr] - reg_pivot[prev_yr]) / reg_pivot[prev_yr].abs() * 100
            ).round(1)

    if not yoy_table.empty:
        def color_yoy(val):
            if pd.isna(val):
                return ""
            color = "#1D9E75" if val >= 0 else "#E24B4A"
            return f"color: {color}; font-weight: 600"

        styler = yoy_table.style
        # pandas >= 2.1: Styler.applymap renamed to .map()
        if hasattr(styler, "map"):
            styled = styler.map(color_yoy).format("{:.1f}%", na_rep="—")
        else:
            styled = styler.applymap(color_yoy).format("{:.1f}%", na_rep="—")
        st.dataframe(styled, use_container_width=True, height=220)
    else:
        st.info("Select multiple years to see YoY growth.")

# SECTION 5 — Customer & Order Analysis
st.markdown('<p class="section-header">Customer & Order Analysis</p>', unsafe_allow_html=True)

col_ship, col_cust, col_disc = st.columns(3)

# Orders by Ship Mode
with col_ship:
    ship_agg = (
        df.groupby("Ship Mode")
        .agg(order_count=("Order ID", "nunique"), avg_ship_days=("ship_days", "mean"))
        .reset_index()
        .sort_values("order_count", ascending=False)
    )
    fig_ship = go.Figure(
        go.Bar(
            x=ship_agg["Ship Mode"],
            y=ship_agg["order_count"],
            marker_color=PRIMARY,
            text=ship_agg["avg_ship_days"].apply(lambda d: f"{d:.1f}d avg"),
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Orders: %{y:,}<br>"
                "Avg Ship Days: %{text}<extra></extra>"
            ),
        )
    )
    fig_ship.update_layout(
        title="Orders by Ship Mode",
        template=CHART_TEMPLATE,
        height=320,
        margin=dict(t=40, b=20, l=10, r=10),
        yaxis_title="Orders",
    )
    st.plotly_chart(fig_ship, use_container_width=True)

# Top 10 customers by revenue
with col_cust:
    seg_color_map = {"Consumer": PRIMARY, "Corporate": GREEN, "Home Office": "#BA7517"}
    top_custs = (
        df.groupby(["Customer Name", "Segment"])
        .agg(total_revenue=("revenue", "sum"))
        .reset_index()
        .nlargest(10, "total_revenue")
        .sort_values("total_revenue")
    )
    top_custs["bar_color"] = top_custs["Segment"].map(seg_color_map)
    fig_cust = go.Figure(
        go.Bar(
            x=top_custs["total_revenue"],
            y=top_custs["Customer Name"],
            orientation="h",
            marker_color=top_custs["bar_color"].tolist(),
            customdata=top_custs["Segment"].values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Revenue: $%{x:,.0f}<br>"
                "Segment: %{customdata}<extra></extra>"
            ),
        )
    )
    fig_cust.update_layout(
        title="Top 10 Customers by Revenue",
        template=CHART_TEMPLATE,
        height=320,
        margin=dict(t=40, b=20, l=10, r=10),
        xaxis_title="Revenue ($)",
    )
    st.plotly_chart(fig_cust, use_container_width=True)

# Discount vs Profit scatter (OLS trendline via NumPy — avoids statsmodels,
# which Plotly's trendline="ols" imports at runtime.)
with col_disc:
    sample_df = df.sample(min(len(df), 2000), random_state=42)
    fig_disc = px.scatter(
        sample_df,
        x="discount_pct",
        y="margin_pct",
        color="Category",
        opacity=0.55,
        labels={"discount_pct": "Discount %", "margin_pct": "Margin %"},
        title="Does Discounting Kill Margin?",
        template=CHART_TEMPLATE,
        color_discrete_sequence=[PRIMARY, GREEN, "#BA7517"],
    )
    x_s = sample_df["discount_pct"].to_numpy(dtype=float)
    y_s = sample_df["margin_pct"].to_numpy(dtype=float)
    mask = np.isfinite(x_s) & np.isfinite(y_s)
    if mask.sum() >= 2 and np.ptp(x_s[mask]) > 0:
        slope, intercept = np.polyfit(x_s[mask], y_s[mask], 1)
        x_line = np.linspace(float(np.nanmin(x_s[mask])), float(np.nanmax(x_s[mask])), 50)
        y_line = slope * x_line + intercept
        fig_disc.add_trace(
            go.Scatter(
                x=x_line,
                y=y_line,
                mode="lines",
                name="OLS trend",
                line=dict(color="#1A1A1A", width=2, dash="dash"),
                hovertemplate=(
                    f"Linear fit: slope {slope:.3f} (margin pp per discount %)"
                    "<extra></extra>"
                ),
            )
        )
    fig_disc.update_layout(
        height=320,
        margin=dict(t=40, b=20, l=10, r=10),
    )
    st.plotly_chart(fig_disc, use_container_width=True)

# SECTION 6 — Data Quality Report
with st.expander("View data quality report"):
    # Rebuild issues by re-running validate on the full dataset
    # (lightweight — just flagging, no re-loading from disk)
    dq_rows = []
    null_counts = df_full.isnull().sum()
    for col, cnt in null_counts[null_counts > 0].items():
        dq_rows.append({"Check": f"Null values — {col}", "Count": int(cnt), "Severity": "Warning"})

    dup_count = df_full.duplicated(subset=["Order ID", "Product ID"], keep=False).sum()
    dq_rows.append({"Check": "Duplicate Order ID + Product ID", "Count": int(dup_count), "Severity": "Info"})

    sales_zero = (df_full["Sales"] <= 0).sum()
    dq_rows.append({"Check": "Sales <= 0", "Count": int(sales_zero), "Severity": "Anomaly"})

    bad_discount = ((df_full["Discount"] < 0) | (df_full["Discount"] > 0.8)).sum()
    dq_rows.append({"Check": "Discount outside 0–0.8", "Count": int(bad_discount), "Severity": "Anomaly"})

    qty_zero = (df_full["Quantity"] <= 0).sum()
    dq_rows.append({"Check": "Quantity <= 0", "Count": int(qty_zero), "Severity": "Anomaly"})

    impossible = (df_full["Profit"] > df_full["Sales"]).sum()
    dq_rows.append({"Check": "Profit > Sales (impossible margin)", "Count": int(impossible), "Severity": "Anomaly"})

    dq_df = pd.DataFrame(dq_rows)

    st.markdown(f"**Total rows loaded:** {len(df_full):,}")

    anomaly_cols = [r for r in dq_rows if r["Severity"] == "Anomaly"]
    total_anomalies = sum(r["Count"] for r in anomaly_cols)
    st.markdown(f"**Total flagged rows:** {total_anomalies:,}")
    st.markdown(f"**Clean rows:** {len(df_full) - total_anomalies:,}")

    st.dataframe(dq_df, use_container_width=True, hide_index=True)

    # Sample of flagged rows
    if "is_anomaly" in df_full.columns:
        flagged = df_full[df_full["is_anomaly"]].head(10)
        if not flagged.empty:
            st.markdown("**Sample flagged rows (first 10):**")
            display_cols = [
                "Order ID", "Product Name", "Sales", "Profit",
                "Discount", "Quantity", "is_anomaly",
            ]
            st.dataframe(
                flagged[[c for c in display_cols if c in flagged.columns]],
                use_container_width=True,
                hide_index=True,
            )

# Footer
st.markdown(
    "<div style='text-align:center; color:#6C757D; font-size:0.85rem;'>"
    "Project 3 of 6 &nbsp;·&nbsp; Data &amp; Business Analyst Portfolio &nbsp;·&nbsp;"
    "Data: <a href='https://www.kaggle.com/datasets/vivek468/superstore-dataset-final' "
    "target='_blank'>Superstore Dataset via Kaggle</a> &nbsp;·&nbsp;"
    "<a href='https://github.com/' target='_blank'>View source on GitHub</a>"
    "</div>",
    unsafe_allow_html=True,
)
