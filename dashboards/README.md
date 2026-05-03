# Dashboards

Two-page Streamlit dashboard reading from the gold KPI table. Page 1 is
the OOS overview; Page 2 is forecast-accuracy diagnostics. Both pages
share tier + country filters in the sidebar.

## Files

- `streamlit_app.py` — the app
- `requirements.txt` — Python deps (streamlit, pandas, plotly, sqlalchemy, psycopg2-binary)
- `sample_kpi.csv` — *not committed*; you create this on demand for demo mode

## Run locally — Postgres mode (production layout)

Reads `portfolio.oos_agent_kpi` directly from Azure PostgreSQL.

```bash
pip install -r dashboards/requirements.txt

export PG_HOST=<your-server>.postgres.database.azure.com
export PG_DB=postgres
export PG_USER=<user>
export PG_PASSWORD=<password>

streamlit run dashboards/streamlit_app.py
```

App opens at <http://localhost:8501>. Data is cached for 10 minutes;
rerun to refresh.

## Run locally — CSV demo mode (no Postgres)

Use this when Postgres isn't provisioned yet. Export the gold table from
Databricks once, then point the app at the CSV.

In a Databricks notebook:

```python
(spark.table("oos_portfolio.gold.oos_agent_kpi")
      .toPandas()
      .to_csv("/Workspace/Users/<you>/sample_kpi.csv", index=False))
```

Download the CSV via the Databricks UI, drop it under `dashboards/sample_kpi.csv`, then:

```bash
export OOS_DATA_SOURCE=csv
export OOS_CSV_PATH=dashboards/sample_kpi.csv
streamlit run dashboards/streamlit_app.py
```

## Deploy to Streamlit Community Cloud (free public URL)

1. Push the repo to GitHub.
2. Sign in at <https://share.streamlit.io> with the same GitHub account.
3. **New app** → pick the repo, branch `main`, main file `dashboards/streamlit_app.py`.
4. **Advanced settings → Secrets**: add the `PG_*` env vars.
   (For the demo path, set `OOS_DATA_SOURCE=csv` and commit a sanitised
   `sample_kpi.csv` so the public app has data to render.)
5. Deploy. URL pattern: `https://<your-handle>-<repo>-<hash>.streamlit.app`.

## Page layout (matches README Day 6 spec)

**Page 1 — OOS Overview**
- KPI cards: total products, OOS count, OOS %, total reorder qty
- Bar: OOS count by tier (T1 / T2 / T3) with % labels
- Bar: OOS rate by country, top 15
- Table: top-20 products by `reorder_qty`

**Page 2 — Forecast Accuracy**
- KPI cards: median WAPE, WAPE-under-50% share, products scored
- Histogram: WAPE distribution (40 bins)
- Table: top-10 worst-WAPE products

## Sanity check before screenshotting

- OOS rate should land 20–30% (driven by `BALANCE_SIM_MULT_LOW/HIGH`)
- Top-20 reorder list should be dominated by T1/T2; if it's all T3, your
  forecast is collapsing toward zero — check `04_compute_forecast`
- Median WAPE 0.3–0.6 is normal for UCI; >0.8 means the bias-correction
  step (`05_compute_backtest`) didn't run or didn't write `wape` into gold
