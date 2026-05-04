"""Retail OOS dashboard — 2-page Streamlit app.

Reads from Azure SQL Database (`oos_portfolio.dbo.oos_agent_kpi`) when
available, or from a local CSV exported from `oos_portfolio.gold.oos_agent_kpi`
when Azure SQL isn't reachable yet (demo mode).

Run locally:
    pip install -r dashboards/requirements.txt
    export AZSQL_HOST=...; export AZSQL_USER=...; export AZSQL_PASSWORD=...
    streamlit run dashboards/streamlit_app.py

Demo mode (no Azure SQL):
    export OOS_DATA_SOURCE=csv
    export OOS_CSV_PATH=dashboards/sample_kpi.csv
    streamlit run dashboards/streamlit_app.py
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Retail OOS Dashboard", layout="wide")

AZSQL_HOST     = os.getenv("AZSQL_HOST",     "")
AZSQL_DB       = os.getenv("AZSQL_DB",       "oos_portfolio")
AZSQL_USER     = os.getenv("AZSQL_USER",     "")
AZSQL_PASSWORD = os.getenv("AZSQL_PASSWORD", "")
AZSQL_TABLE    = os.getenv("AZSQL_TABLE",    "dbo.oos_agent_kpi")

DATA_SOURCE = os.getenv("OOS_DATA_SOURCE", "azsql").lower()  # azsql | csv
CSV_PATH    = os.getenv("OOS_CSV_PATH",    "dashboards/sample_kpi.csv")


# ── Data loading ─────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Loading KPI table…")
def load_kpi() -> pd.DataFrame:
    if DATA_SOURCE == "csv":
        return pd.read_csv(CSV_PATH)

    from sqlalchemy import create_engine
    # mssql+pymssql:// uses the pymssql driver (FreeTDS-based, pure-Python
    # binding in requirements.txt).  Azure SQL negotiates TLS automatically.
    url = (
        f"mssql+pymssql://{AZSQL_USER}:{AZSQL_PASSWORD}@{AZSQL_HOST}:1433/{AZSQL_DB}"
    )
    return pd.read_sql(f"SELECT * FROM {AZSQL_TABLE}", create_engine(url))


# ── Sidebar: source banner + filters ─────────────────────────────
st.sidebar.markdown(f"**Source:** `{DATA_SOURCE}`")
if DATA_SOURCE == "azsql" and not AZSQL_HOST:
    st.sidebar.error("AZSQL_HOST not set. Export it or switch to CSV mode.")
    st.stop()

try:
    df = load_kpi()
except Exception as exc:
    st.error(f"Failed to load data: {exc}")
    st.stop()

# Light type cleanup so filters work uniformly.
for col in ("tier", "country", "balance_color", "stock_code"):
    if col in df.columns:
        df[col] = df[col].astype("string")

page = st.sidebar.radio("Page", ["OOS Overview", "Forecast Accuracy"])

with st.sidebar.expander("Filters", expanded=True):
    tiers     = st.multiselect("Tier",    sorted(df["tier"].dropna().unique()))
    countries = st.multiselect("Country", sorted(df["country"].dropna().unique()))

if tiers:
    df = df[df["tier"].isin(tiers)]
if countries:
    df = df[df["country"].isin(countries)]


# ── Page 1: OOS Overview ─────────────────────────────────────────
if page == "OOS Overview":
    st.title("Retail OOS Overview")

    n_products = len(df)
    n_oos      = int(df["is_oos"].sum()) if "is_oos" in df.columns else 0
    oos_rate   = (n_oos / n_products) if n_products else 0.0
    total_ro   = float(df["reorder_qty"].fillna(0).sum()) if "reorder_qty" in df.columns else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total products",    f"{n_products:,}")
    c2.metric("OOS count",         f"{n_oos:,}")
    c3.metric("OOS rate",          f"{oos_rate:.1%}")
    c4.metric("Total reorder qty", f"{total_ro:,.0f}")

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("OOS by tier")
        tier_df = (
            df.groupby("tier", dropna=False)
              .agg(oos=("is_oos", "sum"), total=("is_oos", "size"))
              .reset_index()
        )
        tier_df["oos_pct"] = tier_df["oos"] / tier_df["total"]
        fig = px.bar(
            tier_df, x="tier", y="oos",
            text=tier_df["oos_pct"].map(lambda v: f"{v:.0%}"),
            labels={"oos": "OOS products"},
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("OOS rate by country (top 15)")
        c_df = (
            df.dropna(subset=["country"])
              .groupby("country")["is_oos"].mean()
              .reset_index()
              .sort_values("is_oos", ascending=False)
              .head(15)
        )
        fig = px.bar(
            c_df, x="country", y="is_oos",
            labels={"is_oos": "OOS rate"},
        )
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top-20 products by reorder qty")
    cols = [c for c in [
        "stock_code", "tier", "country", "current_balance",
        "corrected_forecast", "reorder_qty", "balance_color",
    ] if c in df.columns]
    top = df.sort_values("reorder_qty", ascending=False).head(20)[cols]
    st.dataframe(top, use_container_width=True, hide_index=True)


# ── Page 2: Forecast Accuracy ────────────────────────────────────
elif page == "Forecast Accuracy":
    st.title("Forecast Accuracy")

    if "wape" not in df.columns:
        st.warning("`wape` column missing — run silver/05_compute_backtest first.")
        st.stop()

    valid = df.dropna(subset=["wape"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Median WAPE",      f"{valid['wape'].median():.1%}" if len(valid) else "n/a")
    c2.metric("WAPE < 50% share", f"{(valid['wape'] < 0.5).mean():.1%}" if len(valid) else "n/a")
    c3.metric("Products scored",  f"{len(valid):,}")

    st.divider()
    st.subheader("WAPE distribution")
    fig = px.histogram(valid, x="wape", nbins=40)
    fig.update_xaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top-10 worst-WAPE products")
    cols = [c for c in [
        "stock_code", "tier", "wape",
        "current_balance", "corrected_forecast", "reorder_qty",
    ] if c in valid.columns]
    worst = valid.sort_values("wape", ascending=False).head(10)[cols]
    st.dataframe(worst, use_container_width=True, hide_index=True)
