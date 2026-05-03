# Azure OOS Pipeline Portfolio — 7-Day Plan

**Goal:** Build a portfolio-ready Azure data engineering + ML pipeline (Bronze → Silver → Gold → Dashboard) using a public retail dataset, modeled on a real OOS detection use case.

**Total time:** ~45–55 hrs over 7 days (~6–8 hrs/day)
**Budget:** ~$5–10 in Azure costs (uses free credits)

> **Just want to run the code?** See [`RUNBOOK.md`](./RUNBOOK.md) for the
> step-by-step execute-and-verify guide (local + Databricks). The
> [Testing](#testing) section below covers the SQL queries to confirm
> each layer is healthy.

---

## Repo Name Options

**Enterprise/technical tone:**
- `retail-oos-forecasting-pipeline`
- `inventory-intelligence-pipeline`
- `demand-forecast-delta-lakehouse`

**Azure-stack focused:**
- `azure-retail-oos-detection` ✅ *(recommended)*
- `azure-lakehouse-forecasting`
- `azure-medallion-ml-pipeline`

---

## Architecture Overview

```
UCI Online Retail CSV (split into daily files)
        ↓
   ADLS Gen2 landing zone — registered as Unity Catalog External Location
        ↓
   Auto Loader (cloudFiles) — incremental file ingestion with checkpoint
        ↓
   Unity Catalog: oos_portfolio.bronze.sales              (Delta managed table)
        ↓
   Unity Catalog: oos_portfolio.silver.{history, agent_stats, forecast,
                                        forecast_accuracy, balance_snapshot}
        ↓
   Unity Catalog: oos_portfolio.gold.oos_agent_kpi
        ↓
   Azure PostgreSQL (serving layer)
        ↓
   Power BI (dashboard)

Orchestration: Azure Data Factory — daily trigger 06:00 UTC
```

## Unity Catalog Object Hierarchy

```
oos_portfolio                           ← CATALOG  (top-level namespace)
├── raw                                 ← SCHEMA   (landing zone)
│   └── landing_zone                    ← VOLUME   (raw CSVs, files, models)
├── bronze                              ← SCHEMA
│   └── sales                           ← Delta TABLE (Auto Loader target)
├── silver                              ← SCHEMA
│   ├── oos_history
│   ├── agent_stats
│   ├── oos_forecast
│   ├── oos_forecast_accuracy
│   └── oos_balance_snapshot
└── gold                                ← SCHEMA
    └── oos_agent_kpi
```

> ⚠️ **Use Databricks Free Trial on Azure (14 days)** — *not* Community Edition.
> Community Edition does **NOT** support Unity Catalog or Auto Loader.

---

## Incremental Loading Strategy (3-day drip-feed)

UCI Online Retail is a **static historical dataset**. To genuinely demonstrate
Auto Loader's incremental ingestion, we **split the CSV by date** and drop new
"daily" files over Day 2 / Day 3 / Day 4. The Auto Loader checkpoint will
process only new files on each re-run.

| Day | Action |
|---|---|
| **Day 1** | Split CSV into ~300 daily files locally (one per `InvoiceDate`) |
| **Day 2** | Upload **all-but-last-2-days** files to landing zone → first Auto Loader run (~300 files) |
| **Day 3** | Drop **1 new daily file** into landing zone → re-run Auto Loader (only 1 file processed) |
| **Day 4** | Drop **1 more daily file** → re-run → again only 1 new file processed |

After Day 4 you have **3 real incremental runs** to screenshot for the README.

---

## Notebook Architecture & Master Orchestration

### Notebook tree (final state)

All notebooks live in your Databricks workspace under `/Workspace/Repos/<user>/azure-retail-oos-detection/notebooks/`. The same files live in your GitHub repo under `notebooks/`.

```
notebooks/
├── 00_run_full_pipeline.py             ← MASTER orchestrator (daily ETL)
│
├── setup/                             ← ONE-TIME admin setup (Day 2)
│   ├── 00_run_all_setup.py             ← runs setup notebooks in order
│   ├── 01_storage_credential.sql       ← UC → ADLS managed-identity link
│   ├── 02_external_location.sql        ← register oos-portfolio container
│   ├── 03_catalog_schemas.sql          ← catalog + 4 medallion schemas
│   ├── 04_volume.sql                   ← landing_zone external volume
│   └── 05_grants.sql                   ← (optional) permissions
│
├── config/                            ← shared config used by all ETL nbs
│   └── pipeline_config.py              ← paths, table names, thresholds
│
├── bronze/
│   └── 01_ingest_bronze_autoloader.py
├── silver/
│   ├── 02_compute_history.py
│   ├── 03_compute_agent_stats.py
│   ├── 04_compute_forecast.py
│   ├── 05_compute_backtest.py
│   └── 06_compute_balance_snapshot.py
├── gold/
│   ├── 07_compute_kpis.py
│   └── 08_push_to_postgres.py
└── analysis/
    └── Results_and_Analysis.ipynb      ← portfolio "proof of work" charts
```

### What each notebook does

#### A. One-time setup notebooks (`setup/`) — Day 2 only

These run **once** per environment to provision Unity Catalog objects.
Run in order; each requires the previous to succeed.

| # | Notebook | Purpose | Privilege required |
|---|---|---|---|
| 01 | `setup/01_storage_credential.sql` | **Verify-only.** The storage credential `cred_oos_portfolio` is created manually via Catalog Explorer → External Data → Storage Credentials. This notebook just runs `DESCRIBE STORAGE CREDENTIAL …` and fails fast if it's missing. | **Metastore admin** (for the manual UI step) |
| 02 | `setup/02_external_location.sql` | `CREATE EXTERNAL LOCATION ext_lakehouse` at the `oos-portfolio` container root + `VALIDATE` | **Metastore admin** |
| 03 | `setup/03_catalog_schemas.sql` | `CREATE CATALOG oos_portfolio` + 4 schemas (`raw`, `bronze`, `silver`, `gold`) each with `MANAGED LOCATION` | Catalog creator |
| 04 | `setup/04_volume.sql` | `CREATE EXTERNAL VOLUME oos_portfolio.raw.landing_zone` pointing at `landing/uci_retail/` | Schema owner |
| 05 | `setup/05_grants.sql` | (Optional) `GRANT USE CATALOG`, `READ VOLUME`, `SELECT ON SCHEMA gold` to `account users` | Object owner |
| 00 | `setup/00_run_all_setup.py` | Master setup runner — calls 01→05 sequentially via `dbutils.notebook.run` | Same as above |

> ⚠️ **Run only once** — these are idempotent (`CREATE ... IF NOT EXISTS`) but should not be in the daily pipeline. ADF should NOT call them.

#### B. Daily ETL notebooks (the actual pipeline)

| # | Notebook | Layer | Purpose | Day built |
|---|---|---|---|---|
| 01 | `bronze/01_ingest_bronze_autoloader.py` | Bronze | Auto Loader: landing CSVs → `bronze.sales` Delta | Day 2 |
| 02 | `silver/02_compute_history.py` | Silver | Daily sales aggregation per product | Day 3 |
| 03 | `silver/03_compute_agent_stats.py` | Silver | Tier classification (T1/T2/T3) | Day 3 |
| 04 | `silver/04_compute_forecast.py` | Silver | DOW + trend + monthly lift forecast | Day 3 |
| 05 | `silver/05_compute_backtest.py` | Silver | Walk-forward backtest, WAPE, bias correction | Day 4 |
| 06 | `silver/06_compute_balance_snapshot.py` | Silver | Simulated current balance per product | Day 4 |
| 07 | `gold/07_compute_kpis.py` | Gold | Final OOS KPIs with corrected forecast | Day 5 |
| 08 | `gold/08_push_to_postgres.py` | Gold | JDBC write to Azure PostgreSQL | Day 5 |
| 00 | `00_run_full_pipeline.py` | Master | Orchestrates all 8 ETL notebooks in dependency order | Day 6 |

#### C. Shared config + analysis

| Notebook | Purpose | Day |
|---|---|---|
| `config/pipeline_config.py` | Centralized constants: catalog name, table FQNs, thresholds, JDBC URL | Day 2 |
| `analysis/Results_and_Analysis.ipynb` | Portfolio charts: WAPE histogram, forecast vs actual, OOS rate | Day 7 |

### Master setup runner — `setup/00_run_all_setup.py`

Run this **once on Day 2** to provision all Unity Catalog objects. After it succeeds, you never run it again — daily ETL takes over.

```python
# notebooks/setup/00_run_all_setup.py
# One-time UC setup runner — calls 5 SQL/Python steps in dependency order.
# Idempotent: every step uses CREATE ... IF NOT EXISTS.

from datetime import datetime

def run_step(name, path, timeout=600):
    print(f"▶ START {name}  ({datetime.utcnow().isoformat()})")
    result = dbutils.notebook.run(path, timeout)
    print(f"✔ END   {name}  → {result}")
    return result

# Strict dependency chain — DO NOT reorder
run_step("storage_credential",  "./01_storage_credential")    # admin
run_step("external_location",   "./02_external_location")     # admin (depends on #1)
run_step("catalog_and_schemas", "./03_catalog_schemas")       # depends on #2
run_step("landing_volume",      "./04_volume")                # depends on #3
run_step("grants",              "./05_grants")                # optional

dbutils.notebook.exit("UC setup complete")
```

> **Note:** SQL notebooks return strings via `dbutils.notebook.exit('...')` only in Python notebooks. For pure `.sql` files, the master runner just executes them and checks for absence of errors. Alternatively, wrap each SQL block in a `.py` notebook using `spark.sql("""...""")` if you want richer return values.

### Shared config — `config/pipeline_config.py`

Avoid hard-coding catalog names, table FQNs, or thresholds in every ETL notebook. Centralize them.

> **Why these values?** The thresholds below are calibrated against actual UCI
> Online Retail percentiles (median daily sales £14.22, p25 £7.50, p75 £26.86,
> p95 £79, ~3,941 products, ~305 days). Earlier drafts ported numbers from a
> Zambian mobile-money agent use case (ZMW currency, hourly granularity); those
> values produced nonsensical OOS rates and tier splits on retail data.

```python
# notebooks/config/pipeline_config.py
# Calibrated for UCI Online Retail (GBP, daily granularity, ~3,941 products)

# ── Unity Catalog object names ───────────────────────────────────
CATALOG = "oos_portfolio"
RAW_SCHEMA    = f"{CATALOG}.raw"
BRONZE_SCHEMA = f"{CATALOG}.bronze"
SILVER_SCHEMA = f"{CATALOG}.silver"
GOLD_SCHEMA   = f"{CATALOG}.gold"

# Volume path (Auto Loader watches this)
LANDING_VOLUME = f"/Volumes/{CATALOG}/raw/landing_zone"

# ── Fully-qualified table names ──────────────────────────────────
T_BRONZE_SALES        = f"{BRONZE_SCHEMA}.sales"
T_SILVER_HISTORY      = f"{SILVER_SCHEMA}.oos_history"
T_SILVER_AGENT_STATS  = f"{SILVER_SCHEMA}.agent_stats"
T_SILVER_FORECAST     = f"{SILVER_SCHEMA}.oos_forecast"
T_SILVER_ACCURACY     = f"{SILVER_SCHEMA}.oos_forecast_accuracy"
T_SILVER_BALANCE      = f"{SILVER_SCHEMA}.oos_balance_snapshot"
T_GOLD_KPI            = f"{GOLD_SCHEMA}.oos_agent_kpi"

# ── OOS thresholds ───────────────────────────────────────────────
OOS_THRESHOLD_FLOOR     = 5      # £ floor — ≈ p25 daily sales
OOS_THRESHOLD_DAYS      = 1.0    # threshold = max(floor, forecast × this)
TOPUP_BUFFER_DAYS       = 2.0    # restock target covers this many forecast days
# (No OOS_THRESHOLD_REBAL — no rebalancer concept in retail)

# ── Product tiers (DAILY revenue, not hourly) ────────────────────
TIER_T1_MIN_DAILY       = 30     # £/day → ~22% T1
TIER_T2_MIN_DAILY       = 8      # £/day → ~38% T2  (T3 = remainder ~40%)

# ── Forecast scale-factor clip per tier ──────────────────────────
SCALE_CLIP_T1           = (0.5, 5.0)   # T1: most volatile, widest clip
SCALE_CLIP_T2           = (0.5, 3.0)
SCALE_CLIP_T3           = (0.5, 1.5)   # T3: tight clip (low-volume noise)

# ── Outlier handling ─────────────────────────────────────────────
WINSORIZE_PCT           = 0.95   # p95 cap on extreme daily sales
BIAS_CORRECTION_CLIP    = (0.5, 3.0)

# ── Backtest ─────────────────────────────────────────────────────
BACKTEST_DAYS           = 7
TREND_WINDOW_DAYS       = 45     # UCI dataset is ~305 days; OK
COLD_START_DAYS         = 7
COLD_START_BUFFER       = 1.1

# ── Balance simulation (UCI has no real inventory data) ──────────
BALANCE_SIM_LOOKBACK    = 3      # days of recent sales to base "balance" on
BALANCE_SIM_MULT_LOW    = 0.3
BALANCE_SIM_MULT_HIGH   = 1.5    # → ~25% OOS rate
BALANCE_SIM_SEED        = 42

# ── Currency / display ───────────────────────────────────────────
CURRENCY_SYMBOL         = "£"
CURRENCY_CODE           = "GBP"
```

**Usage in any ETL notebook:**

```python
%run ../config/pipeline_config

sdf_history = spark.table(T_SILVER_HISTORY)
```

The `%run` magic command imports all variables from the config notebook into the current scope — clean, no circular imports, version-controlled in one place.

### Master notebook — `00_run_full_pipeline.py`

This is the **single entry point** for the daily ETL. ADF will call this one notebook (instead of orchestrating 8 separate notebook activities), which simplifies the ADF pipeline and keeps orchestration logic in code where it can be version-controlled.

```python
# notebooks/00_run_full_pipeline.py
# Master orchestrator — runs the full Bronze → Silver → Gold pipeline
# in dependency order. Each child notebook is a self-contained step.

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ── Pipeline parameters (override via ADF widgets) ───────────────
dbutils.widgets.text("run_date",     str(datetime.utcnow().date()))
dbutils.widgets.text("env",          "dev")
dbutils.widgets.text("oos_threshold", "1.0")

run_date      = dbutils.widgets.get("run_date")
env           = dbutils.widgets.get("env")
oos_threshold = dbutils.widgets.get("oos_threshold")

common_params = {
    "run_date":      run_date,
    "env":           env,
    "oos_threshold": oos_threshold,
}

# ── Helper: run a child notebook + log status ────────────────────
def run_step(name, path, timeout=1800, params=None):
    print(f"▶ START {name}  ({datetime.utcnow().isoformat()})")
    result = dbutils.notebook.run(path, timeout, params or common_params)
    print(f"✔ END   {name}  → {result}")
    return result

# ── STEP 1: Bronze (Auto Loader) ─────────────────────────────────
run_step("bronze_autoloader", "./bronze/01_ingest_bronze_autoloader")

# ── STEP 2: Silver — history must run first (forecast depends on it)
run_step("silver_history",    "./silver/02_compute_history")

# ── STEP 3: Silver — agent_stats + forecast can run in parallel
with ThreadPoolExecutor(max_workers=2) as ex:
    f_stats    = ex.submit(run_step, "silver_agent_stats", "./silver/03_compute_agent_stats")
    f_forecast = ex.submit(run_step, "silver_forecast",    "./silver/04_compute_forecast")
    f_stats.result(); f_forecast.result()

# ── STEP 4: Silver — backtest depends on forecast; balance independent
with ThreadPoolExecutor(max_workers=2) as ex:
    f_back = ex.submit(run_step, "silver_backtest", "./silver/05_compute_backtest")
    f_bal  = ex.submit(run_step, "silver_balance",  "./silver/06_compute_balance_snapshot")
    f_back.result(); f_bal.result()

# ── STEP 5: Gold KPIs (depends on all silver tables) ─────────────
run_step("gold_kpis", "./gold/07_compute_kpis")

# ── STEP 6: Push to PostgreSQL (final serving layer) ─────────────
run_step("push_postgres", "./gold/08_push_to_postgres")

# ── Pipeline summary ─────────────────────────────────────────────
dbutils.notebook.exit(f"SUCCESS run_date={run_date} env={env}")
```

### Execution DAG (what actually runs in what order)

```
                  01_bronze_autoloader
                         │
                  02_compute_history
                  ┌──────┴──────┐
                  ▼             ▼
        03_agent_stats    04_compute_forecast
                  └──────┬──────┘
                  ┌──────┴──────┐
                  ▼             ▼
        05_compute_backtest   06_balance_snapshot
                  └──────┬──────┘
                         ▼
                   07_compute_kpis
                         │
                         ▼
                   08_push_to_postgres
```

### Two orchestration options (pick one for Day 6)

**Option A — Master notebook only** (simplest)
- ADF pipeline has **1 activity**: "Run `00_run_full_pipeline`"
- Orchestration logic lives in Python (versioned, tested, portable)
- **Use this for the portfolio** — cleanest demo

**Option B — ADF orchestrates each notebook**
- ADF pipeline has **8 chained activities**, one per notebook
- Visual DAG inside ADF — recruiters can see the dependency graph
- More clicks but visually impressive on screenshots
- Requires re-creating dependencies in ADF JSON

**Recommended:** build Option A first (works in 30 min). If time on Day 6 permits, *also* build Option B for the screenshot.

### Why a master notebook (vs raw ADF)

1. **Faster iteration** — change orchestration logic by editing 1 Python file, no ADF redeploy.
2. **Local-runnable** — you can test the full pipeline by running `00_run_full_pipeline` directly in Databricks without ADF.
3. **Parametric** — widgets let you pass `run_date`, `env`, `oos_threshold` at runtime.
4. **Parallelism** — `ThreadPoolExecutor` runs independent notebooks concurrently; ADF can't do this without complex parallel-activity setup.
5. **Portable** — same pattern works in Databricks Workflows, ADF, or Airflow.

### Each child notebook follows this template

```python
# notebooks/silver/04_compute_forecast.py
# DOW + trend + monthly-lift forecast

# ── Widgets (so master + ADF can pass parameters) ────────────────
dbutils.widgets.text("run_date", "")
dbutils.widgets.text("env",      "dev")
run_date = dbutils.widgets.get("run_date")

# ── Read upstream Silver table ───────────────────────────────────
sdf_history = spark.table("oos_portfolio.silver.oos_history")

# ── Transform (forecast logic here) ──────────────────────────────
sdf_forecast = (sdf_history
    # ... DOW median + trend + monthly factor ...
)

# ── Write downstream Silver table ────────────────────────────────
(sdf_forecast.write
    .format("delta")
    .mode("overwrite")
    .saveAsTable("oos_portfolio.silver.oos_forecast"))

# ── Return value (visible in master orchestrator logs) ───────────
dbutils.notebook.exit(f"forecast rows={sdf_forecast.count()} run_date={run_date}")
```

This template — widgets → read → transform → write → exit — keeps every child notebook **idempotent, parameterized, and self-contained**.

---

# DAY 1 — Foundation: Azure + GitHub + Bronze Upload

**Time: 7–8 hrs**

## Morning (3 hrs) — Accounts & Setup

- [ ] Create Azure free account ($200 credit) — sign up the night before; approval can take 1–4 hrs
- [ ] Sign up for Databricks Community Edition (free, no credit card)
- [ ] Install Azure CLI + Databricks CLI locally
  ```bash
  brew install azure-cli
  pip install databricks-cli
  az login
  ```
- [ ] Create GitHub repo `azure-retail-oos-detection` with this folder structure:
  ```
  azure-retail-oos-detection/
  ├── README.md
  ├── ARCHITECTURE.md
  ├── MAPPING.md
  ├── requirements.txt
  ├── infrastructure/
  ├── etl/
  │   ├── bronze/
  │   ├── silver/
  │   └── gold/
  ├── notebooks/
  ├── dashboards/
  ├── docs/
  └── tests/
  ```
- [ ] Write initial `README.md` with problem statement
- [ ] Create Azure Resource Group:
  ```bash
  az group create --name rg-oos-portfolio --location eastus
  ```

## Afternoon (3 hrs) — Storage + Raw Data

- [ ] Create ADLS Gen2 storage account (enable hierarchical namespace)
- [ ] Create **1 container**: `oos-portfolio`
  - Industry standard for UC-governed setups: a single container holds all
    layers as folders, governance happens at UC layer (not container RBAC)
  - **Azure naming rule:** container names allow only lowercase letters,
    digits, and hyphens — **NO underscores**. So the container is
    `oos-portfolio` (hyphens), while UC catalog/schema names use
    `oos_portfolio` (underscores, since UC identifiers prefer underscores).
  - Folder layout inside `oos-portfolio/`:
    ```
    oos-portfolio/
    ├── landing/uci_retail/      ← raw CSVs (UC volume)
    ├── bronze/                  ← UC managed schema location
    ├── silver/                  ← UC managed schema location
    └── gold/                    ← UC managed schema location
    ```
- [ ] Download UCI Online Retail dataset:
  - Source: https://archive.ics.uci.edu/dataset/352/online+retail
  - Format: Excel (.xlsx)
- [ ] Convert Excel → CSV locally
- [ ] **Split the CSV into daily files** for the drip-feed strategy:
  ```python
  # split_by_date.py — run once locally
  import pandas as pd, os
  df = pd.read_csv("online_retail.csv", parse_dates=["InvoiceDate"])
  df["sale_date"] = df["InvoiceDate"].dt.date
  os.makedirs("daily_files", exist_ok=True)
  for d, group in df.groupby("sale_date"):
      group.drop(columns=["sale_date"]).to_csv(
          f"daily_files/online_retail_{d}.csv", index=False
      )
  print(f"Created {df['sale_date'].nunique()} daily files")
  ```
- [ ] Stage the daily files into 3 buckets locally:
  - **Bucket A** (historical) — all dates except last 2
  - **Bucket B** — second-to-last date (1 file)
  - **Bucket C** — last date (1 file)

## Evening (1–2 hrs) — Data Understanding

- [ ] Open dataset in Pandas locally; document:
  - Columns: `InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country`
  - Row count, date range, null counts, unique products
- [ ] Write `MAPPING.md`:
  - `StockCode` → `agent_id`
  - `daily revenue (Quantity × UnitPrice)` → `total_sales`
  - `Country` → `region`
  - `InvoiceDate` → `tbl_dt` (partition column)
- [ ] Define OOS rule for retail context:
  - `is_oos = current_stock < forecast_daily_sales × 1.0`
- [ ] Commit everything to GitHub

**End of Day 1 deliverable:** GitHub repo live, daily files split locally,
ADLS landing container ready, schema mapping documented.

---

# DAY 2 — Unity Catalog Setup + Auto Loader Bronze Ingestion

**Time: 7–8 hrs**

## Morning Part A (1.5 hrs) — Databricks Workspace + Cluster

- [ ] Spin up **Databricks Free Trial on Azure** workspace (NOT Community Edition)
- [ ] Create a cluster:
  - Runtime: **13.3 LTS or higher** (UC + Auto Loader require this)
  - Access mode: **Single user** or **Shared** (both UC-enabled)
  - Node type: smallest available (Standard_DS3_v2 is fine)

## Morning Part B (1.5 hrs) — Unity Catalog: Storage Credential + External Location

UC needs a way to access ADLS. This is a **one-time setup**.

- [ ] Create an **Azure Databricks Access Connector** (managed identity):
  ```bash
  az databricks access-connector create \
    --resource-group rg-oos-portfolio \
    --name ac-oos-portfolio \
    --location eastus \
    --identity-type SystemAssigned
  ```
- [ ] Get the connector's principal ID:
  ```bash
  az databricks access-connector show \
    --resource-group rg-oos-portfolio \
    --name ac-oos-portfolio --query identity.principalId -o tsv
  ```
- [ ] Grant it **Storage Blob Data Contributor** on your ADLS account:
  ```bash
  az role assignment create \
    --assignee <principal_id> \
    --role "Storage Blob Data Contributor" \
    --scope /subscriptions/<sub>/resourceGroups/rg-oos-portfolio/providers/Microsoft.Storage/storageAccounts/<storage>
  ```
- [ ] Create Storage Credential + External Location — pick **either** Option A (UI) **or** Option B (SQL). Both produce the same result. After this completes, continue to **Part C** to create catalog → schemas → volume.

### Option A — Databricks UI (point-and-click)

In Databricks → **Catalog Explorer** → **External Data**:
  1. **Storage Credentials** → Create:
     - Name: `cred-oos-portfolio`
     - Type: Azure Managed Identity
     - Access Connector ID: paste **resource ID** from Azure portal
       (format: `/subscriptions/<sub>/resourceGroups/rg-oos-portfolio/providers/Microsoft.Databricks/accessConnectors/ac-oos-portfolio`)
  2. **External Locations** → Create **ONE** location at the container root
     (covers all sub-folders: landing, bronze, silver, gold):
     - Name: `ext-lakehouse`
     - URL: `abfss://oos-portfolio@<storage_account>.dfs.core.windows.net/`
     - Storage credential: `cred-oos-portfolio`
  3. Click **Test connection** — must pass before proceeding.

### Option B — SQL (run in a Databricks SQL editor or notebook)

> ⚠️ **Privilege required:** you must be a **metastore admin** to run `CREATE STORAGE CREDENTIAL` and `CREATE EXTERNAL LOCATION`. Account admins can grant this via Account Console → Metastores.

```sql
-- ──────────────────────────────────────────────────────────────────
-- 1. Create the storage credential (links UC to the Access Connector)
-- ──────────────────────────────────────────────────────────────────
-- Replace <sub>, resource group, and connector name with your actual values.
-- The full resource ID can be copied from the Access Connector's Azure
-- portal "Properties" page → "Resource ID".

CREATE STORAGE CREDENTIAL cred_oos_portfolio
  WITH AZURE_MANAGED_IDENTITY
       '/subscriptions/<sub>/resourceGroups/rg-oos-portfolio/providers/Microsoft.Databricks/accessConnectors/ac-oos-portfolio'
  COMMENT 'Managed identity used by UC to access the lakehouse container';

-- Verify
SHOW STORAGE CREDENTIALS;
DESCRIBE STORAGE CREDENTIAL cred_oos_portfolio;


-- ──────────────────────────────────────────────────────────────────
-- 2. Create the external location at the container root
-- ──────────────────────────────────────────────────────────────────
-- One location covers all sub-folders (landing/, bronze/, silver/, gold/).
-- Schemas and volumes created later will inherit access through this.

CREATE EXTERNAL LOCATION ext_lakehouse
  URL 'abfss://oos-portfolio@<storage_account>.dfs.core.windows.net/'
  WITH (STORAGE CREDENTIAL cred_oos_portfolio)
  COMMENT 'Root external location for OOS lakehouse (all medallion layers)';

-- Verify path is reachable + permissions are correct
-- (equivalent to clicking "Test connection" in the UI)
VALIDATE EXTERNAL LOCATION ext_lakehouse;

-- Inspect
SHOW EXTERNAL LOCATIONS;
DESCRIBE EXTERNAL LOCATION ext_lakehouse;


-- ──────────────────────────────────────────────────────────────────
-- 3. (Optional) Grant your user/group access to use this location
-- ──────────────────────────────────────────────────────────────────
-- Needed if you want a non-admin to create schemas/tables under it.

GRANT CREATE EXTERNAL TABLE  ON EXTERNAL LOCATION ext_lakehouse TO `account users`;
GRANT CREATE MANAGED STORAGE ON EXTERNAL LOCATION ext_lakehouse TO `account users`;
GRANT READ FILES             ON EXTERNAL LOCATION ext_lakehouse TO `account users`;
GRANT WRITE FILES            ON EXTERNAL LOCATION ext_lakehouse TO `account users`;
```

> 💡 **Tip:** if `VALIDATE EXTERNAL LOCATION` fails, the most common cause is the RBAC role (Storage Blob Data Contributor) hasn't propagated yet — wait 2–5 minutes and re-run.

## Morning Part C (1 hr) — Create Catalog, Schemas, Volume (full SQL)

Run all of this in a Databricks SQL editor or notebook **after** Part B SQL
has succeeded. Replace `<storage_account>` with your actual ADLS account name.

> 💡 **Pattern:** one external location at the container root (Part B), then each
> schema gets its own MANAGED LOCATION pointing to a sub-folder. UC
> automatically writes managed tables under that location.

### Full UC setup dependency chain (Part B → Part C)

The complete bottom-up order — each step depends on the previous:

```
1. CREATE STORAGE CREDENTIAL cred_oos_portfolio        ← Part B
        ↓ (consumed by)
2. CREATE EXTERNAL LOCATION ext_lakehouse              ← Part B
        ↓ (parent path of all schemas + volumes below)
3. CREATE CATALOG oos_portfolio                        ← Part C below
        ↓
4. CREATE SCHEMA oos_portfolio.raw     (MANAGED LOCATION → /landing/)
5. CREATE SCHEMA oos_portfolio.bronze  (MANAGED LOCATION → /bronze/)
6. CREATE SCHEMA oos_portfolio.silver  (MANAGED LOCATION → /silver/)
7. CREATE SCHEMA oos_portfolio.gold    (MANAGED LOCATION → /gold/)
        ↓
8. CREATE EXTERNAL VOLUME oos_portfolio.raw.landing_zone
   (LOCATION → /landing/uci_retail/)
```

Run steps 3–8 below as one block:

```sql
-- ──────────────────────────────────────────────────────────────────
-- STEP 1: Create the catalog (top-level namespace)
-- ──────────────────────────────────────────────────────────────────
-- MANAGED LOCATION is required on newer Databricks accounts (no default
-- metastore storage root). Pointing at the container root lets each
-- schema's own MANAGED LOCATION nest underneath it.
CREATE CATALOG IF NOT EXISTS oos_portfolio
  MANAGED LOCATION 'abfss://oos-portfolio@<storage_account>.dfs.core.windows.net/'
  COMMENT 'Portfolio project: retail OOS detection pipeline (medallion architecture)';

-- Set as default for this session
USE CATALOG oos_portfolio;

-- Verify
SHOW CATALOGS;
DESCRIBE CATALOG EXTENDED oos_portfolio;


-- ──────────────────────────────────────────────────────────────────
-- STEP 2: Create schemas with MANAGED LOCATIONS (one per medallion layer)
-- ──────────────────────────────────────────────────────────────────
-- Each schema's managed location is a sub-folder of the lakehouse container.
-- All managed tables created in a schema land under its managed location.

CREATE SCHEMA IF NOT EXISTS oos_portfolio.raw
  MANAGED LOCATION 'abfss://oos-portfolio@<storage_account>.dfs.core.windows.net/landing/'
  COMMENT 'Landing zone: raw incoming files via Auto Loader';

CREATE SCHEMA IF NOT EXISTS oos_portfolio.bronze
  MANAGED LOCATION 'abfss://oos-portfolio@<storage_account>.dfs.core.windows.net/bronze/'
  COMMENT 'Bronze layer: ingested raw Delta tables';

CREATE SCHEMA IF NOT EXISTS oos_portfolio.silver
  MANAGED LOCATION 'abfss://oos-portfolio@<storage_account>.dfs.core.windows.net/silver/'
  COMMENT 'Silver layer: cleaned + feature-engineered tables';

CREATE SCHEMA IF NOT EXISTS oos_portfolio.gold
  MANAGED LOCATION 'abfss://oos-portfolio@<storage_account>.dfs.core.windows.net/gold/'
  COMMENT 'Gold layer: business KPI tables';

-- Verify
SHOW SCHEMAS IN oos_portfolio;
DESCRIBE SCHEMA EXTENDED oos_portfolio.bronze;


-- ──────────────────────────────────────────────────────────────────
-- STEP 3: Create the volume (governed folder for non-tabular files)
-- ──────────────────────────────────────────────────────────────────
-- The volume is where Auto Loader watches for new CSVs. Volumes are
-- the UC-native way to manage files (CSVs, models, images, etc.).

CREATE EXTERNAL VOLUME IF NOT EXISTS oos_portfolio.raw.landing_zone
  LOCATION 'abfss://oos-portfolio@<storage_account>.dfs.core.windows.net/landing/uci_retail/'
  COMMENT 'Daily incoming UCI Online Retail CSV files';

-- Verify
SHOW VOLUMES IN oos_portfolio.raw;
DESCRIBE VOLUME oos_portfolio.raw.landing_zone;


-- ──────────────────────────────────────────────────────────────────
-- STEP 4: (Optional) Grant permissions for portfolio demo
-- ──────────────────────────────────────────────────────────────────
-- For a solo portfolio you can skip this. For a multi-user demo:

-- Allow all account users to use the catalog and read everything
GRANT USE CATALOG          ON CATALOG  oos_portfolio TO `account users`;
GRANT USE SCHEMA           ON SCHEMA   oos_portfolio.bronze TO `account users`;
GRANT USE SCHEMA           ON SCHEMA   oos_portfolio.silver TO `account users`;
GRANT USE SCHEMA           ON SCHEMA   oos_portfolio.gold   TO `account users`;
GRANT SELECT               ON SCHEMA   oos_portfolio.gold   TO `account users`;
GRANT READ VOLUME          ON VOLUME   oos_portfolio.raw.landing_zone TO `account users`;


-- ──────────────────────────────────────────────────────────────────
-- STEP 5: Sanity checks
-- ──────────────────────────────────────────────────────────────────
SHOW EXTERNAL LOCATIONS;        -- should show ext-lakehouse
SHOW STORAGE CREDENTIALS;       -- should show cred-oos-portfolio
SHOW CATALOGS;                  -- should show oos_portfolio
SHOW SCHEMAS IN oos_portfolio;  -- raw, bronze, silver, gold
SHOW VOLUMES IN oos_portfolio.raw;  -- landing_zone
```

After this runs, files in the volume are accessible at:
`/Volumes/oos_portfolio/raw/landing_zone/`

And managed tables created later (e.g. `oos_portfolio.bronze.sales`) will
auto-land under `abfss://lakehouse@.../bronze/sales/`.

## Afternoon Part A (1 hr) — Upload Bucket A Files (initial historical load)

- [ ] Use Databricks CLI to upload **Bucket A** files (all-but-last-2-days):
  ```bash
  for f in daily_files_bucketA/*.csv; do
    databricks fs cp "$f" \
      dbfs:/Volumes/oos_portfolio/raw/landing_zone/
  done
  ```
- [ ] Verify in Catalog Explorer → `oos_portfolio.raw.landing_zone` → ~300 files

## Afternoon Part B (3 hrs) — Auto Loader Bronze Ingestion Job

- [ ] Write `etl/bronze/ingest_bronze_autoloader.py`:
  ```python
  from pyspark.sql import functions as F
  from pyspark.sql.types import (StructType, StructField, StringType,
                                  IntegerType, DoubleType, TimestampType)

  schema = StructType([
      StructField("InvoiceNo",   StringType(),    True),
      StructField("StockCode",   StringType(),    True),
      StructField("Description", StringType(),    True),
      StructField("Quantity",    IntegerType(),   True),
      StructField("InvoiceDate", TimestampType(), True),
      StructField("UnitPrice",   DoubleType(),    True),
      StructField("CustomerID",  StringType(),    True),
      StructField("Country",     StringType(),    True),
  ])

  VOLUME      = "/Volumes/oos_portfolio/raw/landing_zone"
  CHECKPOINT  = f"{VOLUME}/_checkpoints/bronze_sales"
  SCHEMA_LOC  = f"{VOLUME}/_schemas/bronze_sales"

  bronze_stream = (
      spark.readStream
          .format("cloudFiles")
          .option("cloudFiles.format", "csv")
          .option("cloudFiles.schemaLocation", SCHEMA_LOC)
          .option("header", "true")
          .schema(schema)
          .load(VOLUME)
          .withColumn("tbl_dt",      F.to_date("InvoiceDate"))
          .withColumn("ingested_at", F.current_timestamp())
          .withColumn("source_file", F.col("_metadata.file_path"))
  )

  (bronze_stream.writeStream
      .format("delta")
      .option("checkpointLocation", CHECKPOINT)
      .option("mergeSchema", "true")
      .partitionBy("tbl_dt")
      .trigger(availableNow=True)        # batch-style: process all new, then exit
      .toTable("oos_portfolio.bronze.sales"))
  ```
- [ ] Run the script in Databricks → first run processes ~300 files
- [ ] Verify with SQL:
  ```sql
  SELECT tbl_dt, COUNT(*) row_count,
         COUNT(DISTINCT source_file) file_count,
         MAX(ingested_at) latest_ingestion
  FROM oos_portfolio.bronze.sales
  GROUP BY tbl_dt ORDER BY tbl_dt DESC;
  ```
- [ ] Take screenshot — this is your **proof of incremental ingestion run #1**
- [ ] Commit script to GitHub

**End of Day 2 deliverable:** Unity Catalog live, Auto Loader Bronze table
populated with ~300 days of historical data.

---

# DAY 3 — Incremental Run #2 + Silver Layer: History + Tier + Forecast

**Time: 7–8 hrs** ⚠️ *Heaviest day — start early*

## Pre-morning (15 min) — Incremental Drop #1

- [ ] Upload **Bucket B** file (1 new day's CSV) to the volume:
  ```bash
  databricks fs cp daily_files_bucketB/online_retail_<date>.csv \
    dbfs:/Volumes/oos_portfolio/raw/landing_zone/
  ```
- [ ] Re-run `ingest_bronze_autoloader.py` → checkpoint detects only the new file
- [ ] Verify: row count for new `tbl_dt` partition appears, others unchanged
- [ ] Screenshot — **proof of incremental ingestion run #2**

## Morning (3 hrs) — Daily Sales History

- [ ] Write `etl/silver/compute_history.py`:
  - Read `oos_portfolio.bronze.sales`
  - Aggregate per product per day: `groupBy(StockCode, tbl_dt).agg(F.sum(Quantity * UnitPrice).alias("daily_sales"))`
  - Write to `oos_portfolio.silver.oos_history` as **Delta** managed table
- [ ] Verify: distinct products, date range, no duplicates

## Midday (2 hrs) — Tier Classification

- [ ] Write `etl/silver/compute_agent_stats.py`:
  - Compute `avg_daily_sales` per `StockCode` over full history
  - Assign tier (uses `TIER_T1_MIN_DAILY` / `TIER_T2_MIN_DAILY` from config):
    - **T1-Gold**: avg_daily_sales ≥ £30
    - **T2-Silver**: £8 ≤ avg_daily_sales < £30
    - **T3-Bronze**: avg_daily_sales < £8
  - Thresholds are calibrated against UCI percentiles (median £14.22 / p25 £7.50 / p75 £26.86)
  - Write to `oos_portfolio.silver.agent_stats` Delta
- [ ] Print tier distribution; expect ~22% T1, ~38% T2, ~40% T3

## Afternoon (3 hrs) — Forecast Model

- [ ] Write `etl/silver/compute_forecast.py`:
  - **DOW median**: `groupBy(StockCode, day_of_week).agg(F.expr("percentile_approx(daily_sales, 0.5)"))`
  - **45-day OLS trend** per product via Spark SQL aggregates (no UDF, no window):
    - `slope = covar_pop(days_ago, daily_sales) / var_pop(days_ago)`
    - `projected_today = trend_avg − slope × avg(days_ago)`  (exact OLS intercept at days_ago=0)
    - `trend_factor = clip(projected_today / overall_median, per-tier ranges)`
    - Products with <2 distinct days → NULL slope → fall back to `trend_factor = 1.0`
  - **Monthly lift factor**: current month median / overall median
  - **Forecast formula**: `forecast = max(dow_median × trend_factor × month_factor, 0)`
  - Write to `oos_portfolio.silver.oos_forecast` Delta
- [ ] Spot-check 5 products manually

**End of Day 3 deliverable:** Incremental run #2 done; history + tiers + forecast running and validated.

---

# DAY 4 — Incremental Run #3 + Backtest + Balance Simulation

**Time: 6–7 hrs**

## Pre-morning (15 min) — Incremental Drop #2

- [ ] Upload **Bucket C** file (final daily CSV) to the volume:
  ```bash
  databricks fs cp daily_files_bucketC/online_retail_<date>.csv \
    dbfs:/Volumes/oos_portfolio/raw/landing_zone/
  ```
- [ ] Re-run `ingest_bronze_autoloader.py` → only the new file is processed
- [ ] Verify with the same SQL as Day 2 — only the new `tbl_dt` partition has a new `latest_ingestion`
- [ ] Screenshot — **proof of incremental ingestion run #3**
- [ ] You now have 3 incremental runs documented for the README

## Morning (3 hrs) — Walk-forward Backtest

- [ ] Write `etl/silver/compute_backtest.py`:
  - Hold out last 7 days as test set
  - For each test day, forecast using only prior data
  - Compute per product:
    - **WAPE** = `sum(|actual - forecast|) / sum(actual)`
    - **bias_correction** = `sum(actual) / sum(forecast)`, clipped to `[0.5, 3.0]`
  - Write to `oos_portfolio.silver.oos_forecast_accuracy` Delta
- [ ] Document results in notebook:
  - Median WAPE
  - % products with WAPE < 50%
  - Distribution of bias correction values

## Afternoon (3–4 hrs) — Balance Snapshot Simulation

- [ ] Write `etl/silver/compute_balance_snapshot.py`:
  - UCI dataset has no real-time inventory balance — simulate it
  - For each product:
    - `current_balance = (sum of last 3 days sales) × random_uniform(0.3, 1.5)`
  - This deliberately creates ~20–30% OOS rate so the dashboard has interesting data
  - Set seed for reproducibility
  - Write to `oos_portfolio.silver.oos_balance_snapshot` Delta

**End of Day 4 deliverable:** 3 incremental runs documented; backtest accuracy + simulated balance snapshot ready.

---

# DAY 5 — Gold Layer + Azure PostgreSQL

**Time: 7–8 hrs**

## Morning (3 hrs) — Gold KPI Computation

- [ ] Write `etl/gold/compute_kpis.py`:
  - Join: `balance_snapshot ⨝ forecast ⨝ accuracy ⨝ agent_stats`
  - Apply bias correction: `corrected_forecast = forecast × bias_correction`
  - Compute KPIs:
    - `oos_threshold = max(OOS_THRESHOLD_FLOOR, corrected_forecast × OOS_THRESHOLD_DAYS)`
      (i.e. `max(£5, corrected_forecast × 1.0)` — £5 ≈ p25 daily sales)
    - `is_oos = current_balance < oos_threshold`
    - `reorder_qty = ceil(max(corrected_forecast × 2.0 - current_balance, 0))`
      (units to add so on-hand covers `TOPUP_BUFFER_DAYS` of forecast demand)
    - `balance_color` (rough bands — balance ≈ ~3 days of sales):
      - GREEN: `current_balance ≥ £80`
      - AMBER: `£25 ≤ current_balance < £80`
      - RED: `current_balance < £25`
  - Write to `oos_portfolio.gold.oos_agent_kpi` Delta
- [ ] Verify: OOS rate (~20–30%), tier breakdown, threshold distribution sensible

## Afternoon (4 hrs) — PostgreSQL + Push

- [ ] Create **Azure Database for PostgreSQL** Flexible Server (B1ms — cheapest tier)
- [ ] Configure firewall: allow Databricks workspace IPs + your local IP
- [ ] Create schema and table:
  ```sql
  CREATE SCHEMA portfolio;
  CREATE TABLE portfolio.oos_agent_kpi (
      stock_code VARCHAR(20),
      country VARCHAR(50),
      tier VARCHAR(15),
      current_balance DECIMAL(12,2),
      corrected_forecast DECIMAL(12,2),
      oos_threshold DECIMAL(12,2),
      is_oos BOOLEAN,
      reorder_qty DECIMAL(12,2),
      balance_color VARCHAR(10),
      wape DECIMAL(5,2),
      observation_date DATE,
      PRIMARY KEY (stock_code, observation_date)
  );
  CREATE INDEX idx_oos_country ON portfolio.oos_agent_kpi(country);
  CREATE INDEX idx_oos_tier ON portfolio.oos_agent_kpi(tier);
  ```
- [ ] Write `etl/gold/push_to_postgres.py` using Spark JDBC:
  ```python
  df.write.format("jdbc").option("url", jdbc_url) \
      .option("dbtable", "portfolio.oos_agent_kpi") \
      .option("user", user).option("password", pwd) \
      .mode("overwrite").save()
  ```
- [ ] Verify data in pgAdmin or DBeaver

**End of Day 5 deliverable:** Gold KPIs in PostgreSQL, queryable.

---

# DAY 6 — Orchestration + Dashboard

**Time: 7–8 hrs**

## Morning (3–4 hrs) — Azure Data Factory Pipeline

- [ ] Create ADF instance in same resource group
- [ ] Create linked services: ADLS Gen2, Databricks, Azure PostgreSQL
- [ ] Build pipeline with **Databricks Notebook activities** chained:
  ```
  bronze_autoloader (Auto Loader, trigger=availableNow)
      ↓
  silver_history
      ↓
  silver_forecast  ──┐
                     ├──→  silver_balance
  silver_backtest  ──┘
      ↓
  gold_kpis
      ↓
  push_postgres
  ```
- [ ] Configure daily trigger at 06:00 UTC
- [ ] Trigger a manual test run end-to-end
- [ ] Add email failure alert via ADF monitoring → Alerts

> 💡 **If ADF blocks you for >2 hrs:** Fall back to **Databricks Workflows** — native, simpler, same result on resume.

## Afternoon (3–4 hrs) — Power BI Dashboard

- [ ] Install Power BI Desktop (Windows only — if Mac, use Power BI Service web editor or **Streamlit** as substitute)
- [ ] Connect to Azure PostgreSQL
- [ ] Build **2 pages** (compressed scope):

  **Page 1: OOS Overview**
  - KPI cards: total products, OOS count, OOS %, total reorder qty
  - Bar chart: OOS count by tier (T1/T2/T3)
  - Map: OOS rate by Country
  - Table: top-20 products by `reorder_qty`

  **Page 2: Forecast Accuracy**
  - WAPE histogram
  - Bias-correction distribution (before/after bar chart)
  - Top-10 worst-forecast products table
  - Forecast vs actual line chart for 3 sample products

- [ ] Publish to Power BI Service free workspace
- [ ] Take screenshots for README

**End of Day 6 deliverable:** Automated daily pipeline + live dashboard.

---

# DAY 7 — Polish, Documentation & Publish

**Time: 6–7 hrs**

## Morning (3 hrs) — Documentation

- [ ] Create architecture diagram in [Excalidraw](https://excalidraw.com) (fastest):
  - UCI CSV → ADLS Bronze → Databricks (Bronze→Silver→Gold) → PostgreSQL → Power BI
  - Show ADF orchestration layer
- [ ] Write `ARCHITECTURE.md` with the diagram embedded
- [ ] Update `README.md` with:
  - **Problem statement** (3–4 sentences — why OOS detection matters in retail)
  - **Architecture diagram** (embedded image)
  - **Tech stack badges**: Azure, Databricks, Delta Lake, Python 3.10, Power BI, PostgreSQL
  - **Results section**:
    - Median WAPE: e.g., 32%
    - OOS detection rate: e.g., 78%
    - Tier distribution: T1 18% / T2 31% / T3 51%
    - Bias-correction impact: e.g., reduced systematic under-forecast by 28%
  - **Dashboard screenshots** (2–3 images)
  - **How to run** (5-step quickstart)
  - **Cost breakdown**: ~$5–10 total

## Midday (2 hrs) — Results Notebook

- [ ] Write `notebooks/Results_and_Analysis.ipynb`:
  - WAPE histogram across all products
  - Forecast vs actual line chart for 3 sample products (one per tier)
  - OOS rate over time (last 30 days)
  - Bias-correction impact: forecast before/after correction
- [ ] This is your **proof of work** — recruiters open this first

## Afternoon (1–2 hrs) — Publish

- [ ] Make repo **public**
- [ ] Add `requirements.txt`:
  ```
  pyspark==3.4.1
  delta-spark==2.4.0
  pandas
  numpy
  scikit-learn
  matplotlib
  ```
- [ ] Add 1 simple unit test in `tests/test_forecast.py`:
  - Test DOW median calculation with known input
- [ ] Final commit + push to main
- [ ] Add project to CV under "Projects":
  > **Azure Retail OOS Detection Pipeline** — End-to-end medallion-architecture data pipeline (Bronze/Silver/Gold) using Azure Data Factory, Databricks (PySpark), Delta Lake, ADLS Gen2, and PostgreSQL; forecast model with walk-forward backtesting (WAPE) and self-updating bias correction; KPIs served to Power BI dashboard.
- [ ] *(Optional, do tomorrow — not Day 7)* Draft LinkedIn post

**End of Day 7 deliverable:** Public GitHub repo + live dashboard + CV entry. ✅

---

## Testing

How to verify each layer is healthy. Run these in order — earlier failures cascade.

### 1. Local unit tests (no Databricks needed)

The forecast math has a few invariants we can pin down with pure Python:

```bash
pip install -r requirements.txt
pytest tests/ -v
```

`tests/test_forecast.py` covers DOW-median behaviour, the OOS-threshold floor,
and the bias-correction clip. Three checks, all should pass in <1s.

### 2. Per-stage validation on Databricks

After running each notebook, paste these into a SQL cell. Expected ranges
are calibrated for UCI Online Retail.

**Bronze — `01_ingest_bronze_autoloader`**
```sql
SELECT tbl_dt, COUNT(*) AS rows,
       COUNT(DISTINCT source_file) AS files,
       MAX(ingested_at) AS latest_ingestion
FROM oos_portfolio.bronze.sales
GROUP BY tbl_dt ORDER BY tbl_dt DESC LIMIT 10;
```
Expect: one row per day; `latest_ingestion` advances only on partitions touched
by the current run (this is the proof of incremental ingestion).

**Silver — history (`02_compute_history`)**
```sql
SELECT COUNT(*) AS rows, COUNT(DISTINCT StockCode) AS products,
       MIN(tbl_dt) AS first_dt, MAX(tbl_dt) AS last_dt
FROM oos_portfolio.silver.oos_history;
```
Expect: ~3,941 products, ~305 days.

**Silver — agent_stats (`03_compute_agent_stats`)** — tier distribution
```sql
SELECT tier, COUNT(*) AS n,
       ROUND(AVG(avg_daily_sales), 2) AS avg_£
FROM oos_portfolio.silver.agent_stats
GROUP BY tier ORDER BY tier;
```
Expect roughly **T1 ~22% / T2 ~38% / T3 ~40%**. Wildly different splits ⇒
`TIER_T*_MIN_DAILY` thresholds in `pipeline_config.py` need re-tuning.

**Silver — forecast (`04_compute_forecast`)** — trend factor sanity
```sql
SELECT tier,
       percentile_approx(trend_factor, array(0.1, 0.5, 0.9)) AS p10_p50_p90,
       SUM(CASE WHEN trend_factor = 1.0 THEN 1 ELSE 0 END) AS n_fallback,
       COUNT(*) AS n_rows
FROM oos_portfolio.silver.oos_forecast
GROUP BY tier ORDER BY tier;
```
Expect: p50 close to 1.0; T3 has the most `n_fallback=1.0` rows (sparse
products with <2 distinct active days fall back via NULL slope).

**Silver — backtest (`05_compute_backtest`)** — accuracy
```sql
SELECT percentile_approx(wape, array(0.25, 0.5, 0.75)) AS wape_quartiles,
       AVG(CAST((wape < 0.5) AS INT))                  AS pct_under_50,
       COUNT(*)                                        AS n_products
FROM oos_portfolio.silver.oos_forecast_accuracy;
```
Expect: median WAPE in 0.3–0.6 (UCI is volatile); ≥50% of products under 50% WAPE.

**Gold — KPIs (`07_compute_kpis`)** — headline OOS metrics
```sql
SELECT COUNT(*)                                            AS n_products,
       SUM(CASE WHEN is_oos THEN 1 ELSE 0 END)             AS n_oos,
       ROUND(AVG(CASE WHEN is_oos THEN 1.0 ELSE 0.0 END), 3) AS oos_rate,
       SUM(reorder_qty)                                    AS total_reorder_qty
FROM oos_portfolio.gold.oos_agent_kpi;
```
Expect: `oos_rate` ~0.20–0.30 (driven by `BALANCE_SIM_MULT_LOW/HIGH = 0.3 / 1.5`).
If it's near 0 or near 1, the simulation multiplier is mis-tuned.

**Postgres — push (`08_push_to_postgres`)**
```sql
SELECT COUNT(*), MAX(observation_date) FROM portfolio.oos_agent_kpi;
SELECT * FROM portfolio.oos_agent_kpi WHERE is_oos LIMIT 10;
```
Row count must equal the gold table; if it's smaller, JDBC silently dropped
rows (usually an SSL/firewall hiccup).

### 3. End-to-end smoke test

Run the master orchestrator from a notebook cell:

```python
dbutils.notebook.run(
    "./00_run_full_pipeline", 1800,
    {"run_date": "2026-05-03", "env": "dev"}
)
```

Healthy run prints `START … / END … -> …` for all eight steps and exits
with `SUCCESS run_date=… env=dev`.

### 4. Auto Loader incremental-ingestion proof

This is the screenshot recruiters look for. After each daily-file drop:

```sql
SELECT tbl_dt, COUNT(*) AS rows, MAX(ingested_at) AS latest_ingestion
FROM oos_portfolio.bronze.sales
GROUP BY tbl_dt ORDER BY tbl_dt DESC;
```

Only the **new** `tbl_dt` should have a newer `latest_ingestion`. If older
partitions also re-ingest, the checkpoint is mis-configured (most often the
`_checkpoints` folder was deleted between runs).

---

## Daily Time Budget Summary

| Day | Focus | Est. Hours | Critical Path Risk |
|---|---|---|---|
| 1 | Setup + CSV split + landing zone | 7–8 | Azure account approval (1–4 hrs) |
| 2 | UC catalog/schema/volume + Auto Loader Bronze | **7–8** | Storage credential / external location config |
| 3 | Incremental run #2 + Silver: history + tier + forecast | **7–8** | Heaviest day — start early |
| 4 | Incremental run #3 + Backtest + balance simulation | 6–7 | — |
| 5 | Gold KPIs + PostgreSQL | 7–8 | PostgreSQL firewall config |
| 6 | ADF orchestration + Power BI | 7–8 | ADF first-time learning curve |
| 7 | Docs + publish | 6–7 | Buffer for spillover |

**Total: ~48–54 hours**

---

## Critical Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Azure account approval delay | Sign up the night before Day 1 |
| Community Edition lacks UC + Auto Loader | Use **Databricks Free Trial on Azure** (14 days, full features) |
| Storage credential test fails | Confirm RBAC role propagated (~5 min); use Access Connector managed identity, not SP keys |
| Auto Loader checkpoint corruption on re-runs | Never delete `_checkpoints` folder mid-test — clears file-tracking state |
| PostgreSQL JDBC driver issues | Pre-download driver JAR; attach to cluster init script |
| ADF learning curve | If stuck >2 hrs, use **Databricks Workflows** instead |
| Power BI on Mac | Use Power BI Service web editor, or **Streamlit** as substitute |
| Forecast WAPE looks bad | UCI dataset is volatile; document honestly + show bias correction improvement |

---

## What Was Cut From the Original 20-Day Plan

| Cut | Reason |
|---|---|
| Bicep/Terraform IaC | Nice-to-have, not critical for resume credibility |
| GitHub Actions CI | Adds polish but doesn't change the project's substance |
| LinkedIn article on Day 18 | Better written *after* a week of using the project |
| 4-page Power BI dashboard | 2 pages tell the same story — diminishing returns |
| Cost optimization deep-dive | Mention briefly in README; not a Day's worth of work |
| Multiple unit tests | One representative test is enough for portfolio context |

---

## Resume Bullet (after completion)

> Architected an **end-to-end Azure data pipeline** (ADF, Databricks PySpark, **Unity Catalog**, **Auto Loader**, Delta Lake, ADLS Gen2, PostgreSQL) implementing **medallion architecture** (Bronze→Silver→Gold) for retail stock-out detection across 4,000+ products; ingested incremental daily files via `cloudFiles` with checkpoint-based file tracking; engineered a **DOW + trend + monthly-lift forecast model** with **walk-forward backtesting** (WAPE) and **self-updating bias correction**, served KPIs to a **Power BI dashboard** via daily-orchestrated pipelines.

---

## Quick Daily Checklist (print this)

- [ ] **Day 1** — Azure + GitHub + CSV split into daily files + landing zone live
- [ ] **Day 2** — UC catalog/schema/volume + Auto Loader Bronze (run #1)
- [ ] **Day 3** — Incremental run #2 + Silver: history + tiers + forecast
- [ ] **Day 4** — Incremental run #3 + Backtest (WAPE) + simulated balance
- [ ] **Day 5** — Gold KPIs + PostgreSQL serving
- [ ] **Day 6** — ADF pipeline + Power BI dashboard
- [ ] **Day 7** — Docs + public repo + CV updated
