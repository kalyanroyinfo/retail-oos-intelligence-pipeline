# Azure OOS Pipeline Portfolio — 7-Day Plan

**Goal:** Build a portfolio-ready Azure data engineering + ML pipeline (Bronze → Silver → Gold → Dashboard) using a public retail dataset, modeled on a real OOS detection use case.

**Total time:** ~45–55 hrs over 7 days (~6–8 hrs/day)
**Budget:** ~$5–10 in Azure costs (uses free credits)

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
- [ ] Create **1 container**: `lakehouse`
  - Industry standard for UC-governed setups: a single container holds all
    layers as folders, governance happens at UC layer (not container RBAC)
  - Folder layout inside `lakehouse/`:
    ```
    lakehouse/
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
     - URL: `abfss://lakehouse@<storage_account>.dfs.core.windows.net/`
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
  URL 'abfss://lakehouse@<storage_account>.dfs.core.windows.net/'
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
CREATE CATALOG IF NOT EXISTS oos_portfolio
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
  MANAGED LOCATION 'abfss://lakehouse@<storage_account>.dfs.core.windows.net/landing/'
  COMMENT 'Landing zone: raw incoming files via Auto Loader';

CREATE SCHEMA IF NOT EXISTS oos_portfolio.bronze
  MANAGED LOCATION 'abfss://lakehouse@<storage_account>.dfs.core.windows.net/bronze/'
  COMMENT 'Bronze layer: ingested raw Delta tables';

CREATE SCHEMA IF NOT EXISTS oos_portfolio.silver
  MANAGED LOCATION 'abfss://lakehouse@<storage_account>.dfs.core.windows.net/silver/'
  COMMENT 'Silver layer: cleaned + feature-engineered tables';

CREATE SCHEMA IF NOT EXISTS oos_portfolio.gold
  MANAGED LOCATION 'abfss://lakehouse@<storage_account>.dfs.core.windows.net/gold/'
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
  LOCATION 'abfss://lakehouse@<storage_account>.dfs.core.windows.net/landing/uci_retail/'
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
  - Assign tier:
    - **T1-Gold**: avg_daily_sales ≥ 50
    - **T2-Silver**: 10 ≤ avg_daily_sales < 50
    - **T3-Bronze**: avg_daily_sales < 10
  - (Adjust thresholds to match dataset scale — the UCI dataset is in GBP)
  - Write to `oos_portfolio.silver.agent_stats` Delta
- [ ] Print tier distribution; aim for ~20% T1, ~30% T2, ~50% T3

## Afternoon (3 hrs) — Forecast Model

- [ ] Write `etl/silver/compute_forecast.py`:
  - **DOW median**: `groupBy(StockCode, day_of_week).agg(F.expr("percentile_approx(daily_sales, 0.5)"))`
  - **45-day OLS trend slope** per product (use Spark window or pandas UDF on small grouped data)
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
    - `oos_threshold = max(100, corrected_forecast × 1.0)`
    - `is_oos = current_balance < oos_threshold`
    - `float_required = ceil(max(corrected_forecast × 2.0 - current_balance, 0))`
    - `balance_color`:
      - GREEN: `current_balance ≥ 500`
      - AMBER: `100 ≤ current_balance < 500`
      - RED: `current_balance < 100`
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
      float_required DECIMAL(12,2),
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
  - KPI cards: total products, OOS count, OOS %, total float required
  - Bar chart: OOS count by tier (T1/T2/T3)
  - Map: OOS rate by Country
  - Table: top-20 products by `float_required`

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
