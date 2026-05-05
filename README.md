# Retail OOS Intelligence Pipeline

End-to-end Azure data engineering pipeline for retail Out-of-Stock (OOS)
detection. Built on the medallion architecture (Bronze → Silver → Gold)
with Unity Catalog on Databricks.

---

## Project overview

The pipeline ingests daily retail transaction files, computes per-product
sales history + tier classification + a forecast model, runs a
walk-forward backtest, simulates current inventory, and writes a final
KPI table that flags Out-of-Stock products and recommends reorder
quantities.

Key model components (built per-product, ~3,941 products):

- **Day-of-week median** of daily sales as the seasonal baseline
- **OLS trend slope** over the last 45 days, projected to today
- **Monthly lift factor** for current calendar-month seasonality
- **Walk-forward backtest** on the last 7 days, computing WAPE per product
- **Self-updating bias correction** clipped to `[0.5, 3.0]`

The output (`oos_portfolio.gold.oos_agent_kpi`) gives a buyer:
`is_oos`, `corrected_forecast`, `oos_threshold`, `reorder_qty`,
`balance_color` (GREEN / AMBER / RED), and per-product `wape`.

## Dataset

**UCI Online Retail** — <https://archive.ics.uci.edu/dataset/352/online+retail>

- ~500,000 transactional rows over ~305 days
- ~3,941 unique products (`StockCode`)
- 38 countries
- Currency: GBP (`£`)
- License: CC BY 4.0

The static CSV is split per `InvoiceDate` into ~305 daily files locally,
then drip-fed into the landing zone to demonstrate Auto Loader's
incremental ingestion (3 separate runs across separate "buckets" of files).

See `MAPPING.md` for the source-to-domain column mapping.

---

## Azure features used

| Service | Role in the pipeline |
|---|---|
| **Azure Data Lake Storage Gen 2** | Raw + medallion file storage; container `oos-portfolio` with hierarchical namespace |
| **Access Connector for Azure Databricks** | Managed-identity bridge between Unity Catalog and ADLS (no keys) |
| **Azure Databricks (Premium)** | Spark compute, Delta Lake, Unity Catalog, Auto Loader |
| **Unity Catalog** | Catalog / schemas / external location / volume governance |
| **Delta Lake** | Table format for all bronze / silver / gold tables |
| **Auto Loader (`cloudFiles`)** | Incremental file ingestion with checkpoints |
| **Azure SQL Database** | Serving layer — gold KPIs queryable via standard SQL |
| **azcopy + SAS** | One-time bulk upload of historical CSVs into the landing zone |
| *(Optional)* **Azure Data Factory** | Daily orchestration of the master notebook |
| *(Optional)* **Log Analytics** | Pipeline run / failure observability via KQL |
| *(Optional)* **Databricks Secret Scope** | Hides Azure SQL credentials at runtime |

---

## Architecture

```
UCI CSV → ADLS Gen 2 (landing/) → Databricks Auto Loader
                                    ↓
                       Bronze: oos_portfolio.bronze.sales
                                    ↓
                       Silver: history → agent_stats → forecast
                                    │
                       Silver: backtest │ balance_snapshot
                                    ↓
                       Gold:   oos_portfolio.gold.oos_agent_kpi
                                    ↓ (Spark JDBC)
                       Azure SQL Database: dbo.oos_agent_kpi
```

Orchestration: Azure Data Factory (or Databricks Workflows / manual)
trigger of `notebooks/00_run_full_pipeline.py`.

Full diagram and resource names: `ARCHITECTURE.md`.

---

## Project structure

```
retail-oos-intelligence-pipeline/
├── README.md                         ← this file
├── ARCHITECTURE.md                   ← architecture diagram + resource names
├── MAPPING.md                        ← UCI → domain column mapping
├── infrastructure/README.md          ← Azure provisioning walkthrough
├── notebooks/
│   ├── 00_run_full_pipeline.py       ← master orchestrator
│   ├── setup/                        ← one-time UC provisioning (5 SQL files + runner)
│   ├── config/pipeline_config.py     ← shared constants
│   ├── bronze/01_ingest_bronze_autoloader.py
│   ├── silver/02_compute_history.py
│   ├── silver/03_compute_agent_stats.py
│   ├── silver/04_compute_forecast.py        ← OLS trend + DOW + monthly lift
│   ├── silver/05_compute_backtest.py        ← walk-forward, WAPE, bias correction
│   ├── silver/06_compute_balance_snapshot.py
│   ├── gold/07_compute_kpis.py
│   ├── gold/08_push_to_azure_sql.py         ← serving-layer JDBC write
│   ├── maintenance/                  ← reset_bronze / reset_silver_gold / reset_all
│   └── analysis/Results_and_Analysis.ipynb  ← portfolio "proof of work" charts
├── scripts/split_by_date.py          ← split CSV into daily files
└── tests/test_forecast.py            ← local unit tests for the forecast math
```

---

## Quick start

```bash
# 1. Clone + local sanity tests
git clone <repo-url> retail-oos-intelligence-pipeline
cd retail-oos-intelligence-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v

# 2. Split UCI CSV into daily files (one-time)
python scripts/split_by_date.py --src online_retail.csv --out daily_files

# 3. Upload to ADLS via azcopy (see infrastructure/README.md Step 11)
azcopy copy "daily_files/*.csv" \
  "https://oosstorage.blob.core.windows.net/oos-portfolio/landing/uci_retail/${SAS}"
```

Then in Databricks:

```python
# 4. Run the master orchestrator — Bronze through Gold + Azure SQL push
dbutils.notebook.run("./notebooks/00_run_full_pipeline", 1800)
```

---

## How to run — phase by phase

### Phase 1 — Local prep

**Unit tests:**

```bash
pytest tests/ -v
```

Three checks (DOW median, OOS-threshold floor, bias-correction clip) pass in <1s.

**Split the UCI CSV:**

Prereq: download `online_retail.xlsx` from
<https://archive.ics.uci.edu/dataset/352/online+retail>, convert to CSV,
place at repo root as `online_retail.csv`.

```bash
python scripts/split_by_date.py --src online_retail.csv --out daily_files
```

Optionally split into 3 buckets to demo Auto Loader's incremental ingestion (3 separate runs):

```bash
mkdir -p daily_files_bucketA daily_files_bucketB daily_files_bucketC
ls daily_files | sort | head -n -2 | xargs -I{} mv daily_files/{} daily_files_bucketA/
ls daily_files | sort | head -n 1   | xargs -I{} mv daily_files/{} daily_files_bucketB/
mv daily_files/* daily_files_bucketC/
```

### Phase 2 — Azure infrastructure (one-time)

Follow `infrastructure/README.md` for the full Portal walkthrough — 11 steps:

1. Resource Group `rg-oos-portfolio`
2. Access Connector for Databricks `ac-oos-portfolio`
3. Storage Account `oosstorage` (HNS enabled) + container `oos-portfolio`
4. RBAC: `Storage Blob Data Contributor` → Access Connector
5. Databricks workspace `dbw-oos-portfolio` (**Premium tier**)
6. Cluster (and optional SQL warehouse)
7. Storage Credential `cred_oos_portfolio` in Unity Catalog
8. External Location `ext_lakehouse`
9. Catalog + schemas + volume (`notebooks/setup/00_run_all_setup.py`)
10. Azure SQL Database `oos_portfolio` + `dbo.oos_agent_kpi` table
11. Upload historical CSVs via `azcopy` + SAS

### Phase 3 — Run the pipeline

**Master orchestrator (recommended):**

```python
dbutils.notebook.run("./notebooks/00_run_full_pipeline", 1800)
```

Bronze → Silver (with parallel branches) → Gold → Azure SQL push.
Total runtime: ~5–8 min.

**Or run notebooks individually:**

| Order | Notebook | Approx. runtime |
|---|---|---|
| 1 | `bronze/01_ingest_bronze_autoloader` | 30–90 s |
| 2 | `silver/02_compute_history` | 30 s |
| 3 | `silver/03_compute_agent_stats` | 20 s |
| 4 | `silver/04_compute_forecast` | 60 s |
| 5 | `silver/05_compute_backtest` | 60 s |
| 6 | `silver/06_compute_balance_snapshot` | 20 s |
| 7 | `gold/07_compute_kpis` | 30 s |
| 8 | `gold/08_push_to_azure_sql` | 60–120 s |

### Phase 4 — Verify

Sanity SQL — paste into any Databricks SQL cell:

```sql
-- Bronze: row counts + ingestion timestamps
SELECT tbl_dt, COUNT(*) AS rows, MAX(ingested_at) AS latest_ingestion
FROM oos_portfolio.bronze.sales
GROUP BY tbl_dt ORDER BY tbl_dt DESC LIMIT 10;

-- Silver: tier distribution should be ~22 / 38 / 40
SELECT tier, COUNT(*) AS n FROM oos_portfolio.silver.agent_stats GROUP BY tier ORDER BY tier;

-- Silver: forecast accuracy
SELECT percentile_approx(wape, array(0.25, 0.5, 0.75)) AS quartiles,
       AVG(CAST((wape < 0.5) AS INT))                  AS pct_under_50
FROM oos_portfolio.silver.oos_forecast_accuracy;

-- Gold: headline KPIs
SELECT COUNT(*)                                            AS n_products,
       SUM(CASE WHEN is_oos THEN 1 ELSE 0 END)             AS n_oos,
       ROUND(AVG(CASE WHEN is_oos THEN 1.0 ELSE 0.0 END), 3) AS oos_rate,
       SUM(reorder_qty)                                    AS total_reorder_qty
FROM oos_portfolio.gold.oos_agent_kpi;
```

Then in Azure SQL Query editor:

```sql
SELECT COUNT(*), MAX(observation_date) FROM oos_portfolio.dbo.oos_agent_kpi;
```

Row count should match `oos_portfolio.gold.oos_agent_kpi` on Databricks.

Expected ranges (UCI dataset): ~3,941 products, OOS rate 0.20–0.30, median WAPE 0.30–0.60.

### Phase 5 — Generate analysis charts

The portfolio "proof of work" notebook lives at
`notebooks/analysis/Results_and_Analysis.ipynb` — 11 charts / tables across
5 sections (data overview, tier story, forecast methodology, forecast
accuracy, OOS outcomes).

To run:

1. Open the notebook in Databricks
2. Attach to your cluster
3. **Run all**

Sections produced:

| Section | Output |
|---|---|
| **A.1** Data shape card | rows / products / date range / countries |
| **A.2** Daily revenue over time | line chart |
| **B.1** Tier composition + revenue Pareto | grouped bar (% products vs % revenue) |
| **C.1** Day-of-week seasonality | bar chart per DOW |
| **C.2** Trend factor distribution per tier | 3-pane histogram |
| **D.1** WAPE histogram | overall accuracy distribution |
| **D.2** WAPE summary metrics | median / pooled / quartiles / share-under-50% |
| **D.3** WAPE by tier | one-row-per-tier table |
| **D.4** Worst-forecast products | top-10 table |
| **E.1** OOS rate by country | bar chart, top 15 |
| **E.2** Inventory health (balance colors) | GREEN / AMBER / RED breakdown |
| **E.3** Reorder-qty Pareto | cumulative-share line with 80% reference |

Cells gracefully skip if upstream tables haven't been built yet, so the
notebook can be run after just Bronze, after Silver, etc.

---

## Resets — start a layer over

`notebooks/maintenance/` contains 3 dry-run-by-default reset scripts:

| Notebook | Wipes | Keeps |
|---|---|---|
| `reset_bronze.py` | Landing volume contents + Bronze table | Silver, Gold |
| `reset_silver_gold.py` | All Silver + Gold tables | Bronze, landing |
| `reset_all.py` | Everything above (chains both) | Setup objects |

Each defaults to **DRY-RUN** — set the widget `confirm = YES` to actually delete.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `VALIDATE EXTERNAL LOCATION` fails | RBAC propagation delay | Wait 2–5 min, retry |
| `CREATE CATALOG` fails: "Metastore storage root URL does not exist" | Newer Databricks account | Already handled — `03_catalog_schemas.sql` sets explicit `MANAGED LOCATION` |
| Bronze produces 0 rows | Files missing in volume, or checkpoint already saw them | `LIST '/Volumes/oos_portfolio/raw/landing_zone/'`; if needed run `reset_bronze` |
| Tier distribution wildly off | Threshold mismatch with currency/granularity | Check `TIER_T*_MIN_DAILY` in `pipeline_config.py` |
| `trend_factor = 1.0` for everyone | Trend filter too aggressive | Inspect `sdf_trend` after `.filter(isNotNull)` in `04_compute_forecast` |
| `oos_rate` is 0% or 100% | `BALANCE_SIM_MULT_LOW/HIGH` mis-tuned | Tweak in `pipeline_config.py` |
| `08_push_to_azure_sql` PK violation | Duplicate `(stock_code, observation_date)` rows | The notebook auto-dedupes; `02_compute_history` normalizes `StockCode` upstream |
| `08_push_to_azure_sql` hangs | Azure SQL firewall blocks Databricks | Portal → SQL server → Networking → tick "Allow Azure services" |
| `Login failed for user` | Wrong password, or used `<user>@<server>` legacy syntax | Use just `oosadmin` for SQL auth |
| Auto Loader re-ingests old files | Checkpoint deleted between runs | Don't delete `_checkpoints/`; otherwise `reset_bronze` to start clean |

---

## Cost

Cheapest-tier Azure resources, all running:

| Resource | Approx. monthly cost |
|---|---|
| Storage account (LRS, ~50 MB) | < $0.10 |
| Access connector | $0 |
| Databricks workspace | $0 idle; cluster at ~$0.40–0.80/hr while running |
| Azure SQL (Basic, 5 DTU) | ~$5 |
| **Total when actively iterating** | **~$5–10/month** |

Pause the SQL DB and stop the cluster between sessions to minimize.

---

## What this project demonstrates

- **Medallion architecture** with Unity Catalog governance
- **Incremental ingestion** via Auto Loader checkpoints (3 documented runs)
- **Spark SQL aggregates** for time-series analytics — `covar_pop`,
  `var_pop`, `percentile_approx`, window functions
- **Data quality discipline** — `StockCode` whitespace/case normalization
  in silver to satisfy a downstream relational PK constraint
- **Walk-forward backtesting** with WAPE + self-updating bias correction
- **Idempotent ETL** — every notebook uses overwrite mode, master
  orchestrator can rerun safely
- **Defensive operational design** — reset notebooks for each layer,
  table-availability guards in the analysis notebook
- **Serving-layer integration** via Spark JDBC to Azure SQL
- **Observability hooks** — Log Analytics + KQL queries for ADF /
  Databricks diagnostic logs
- **Manual provisioning playbook** — every Azure resource documented
  in `infrastructure/README.md` for repeatability

---

## References

- [`infrastructure/README.md`](infrastructure/README.md) — Azure setup, step by step
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — diagram + resource names
- [`MAPPING.md`](MAPPING.md) — source-to-domain column mapping
- [`notebooks/maintenance/README.md`](notebooks/maintenance/README.md) — reset scripts
- [UCI Online Retail dataset](https://archive.ics.uci.edu/dataset/352/online+retail)
