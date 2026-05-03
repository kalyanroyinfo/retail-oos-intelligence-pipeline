# Runbook — How to Execute & Verify Each Script

Step-by-step recipe for running everything in this repo and confirming it
works. Pair this with the **Testing** section in `README.md` (the canned
SQL queries) — the runbook tells you *how* to run, the README tells you
*what to look for in the result*.

There are two execution surfaces:

- **Local** (your laptop) — unit tests, the CSV splitter, the Streamlit dashboard
- **Databricks** (workspace) — every notebook under `notebooks/`

---

## Part 1 — Local

### 1.1 Clone & set up the environment

```bash
git clone <your-repo-url> retail-oos-intelligence-pipeline
cd retail-oos-intelligence-pipeline

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Verify: `python -c "import pandas, pyspark"` should print nothing (no error).

### 1.2 Run the forecast unit tests

```bash
pytest tests/ -v
```

Expected output:
```
tests/test_forecast.py::test_dow_median_simple PASSED
tests/test_forecast.py::test_oos_threshold_floor PASSED
tests/test_forecast.py::test_bias_correction_clip PASSED
3 passed in 0.0Xs
```

If you don't have pytest installed, the same checks run via:
```bash
python3 -c "
import sys; sys.path.insert(0, 'tests')
import test_forecast as t
t.test_dow_median_simple(); t.test_oos_threshold_floor(); t.test_bias_correction_clip()
print('OK')
"
```

### 1.3 Split the UCI CSV into daily files

Prereq: download `online_retail.xlsx` from
<https://archive.ics.uci.edu/dataset/352/online+retail>, convert to CSV
(Excel → "Save as CSV"), and place it at the repo root as `online_retail.csv`.

```bash
python scripts/split_by_date.py --src online_retail.csv --out daily_files
```

Expected: `Created 305 daily files in daily_files/` (give or take a couple
depending on the version of the dataset). Spot-check one:

```bash
ls daily_files/ | head -5
head -3 daily_files/online_retail_2010-12-01.csv
```

Then split that into the 3 buckets the README plan calls for:

```bash
mkdir -p daily_files_bucketA daily_files_bucketB daily_files_bucketC
ls daily_files | sort | head -n -2 | xargs -I{} mv daily_files/{} daily_files_bucketA/
ls daily_files | sort | head -n 1   | xargs -I{} mv daily_files/{} daily_files_bucketB/
mv daily_files/* daily_files_bucketC/   # whatever's left = last day
```

### 1.4 Run the Streamlit dashboard (CSV demo mode)

You need a `sample_kpi.csv` first — see Part 2 step 2.11 to export one
from Databricks. Once you have it:

```bash
pip install -r dashboards/requirements.txt
export OOS_DATA_SOURCE=csv
export OOS_CSV_PATH=dashboards/sample_kpi.csv
streamlit run dashboards/streamlit_app.py
```

Expected: a tab opens at <http://localhost:8501> showing the OOS Overview
page. Sidebar shows `Source: csv`. Switch pages via the sidebar radio.

If you see `Failed to load data: [Errno 2] No such file or directory`, the
CSV path is wrong — fix `OOS_CSV_PATH`.

---

## Part 2 — Databricks

Prereq: a **Databricks Free Trial on Azure** workspace (NOT Community
Edition), and the Azure resources from `README.md` Day 1–2 already
provisioned (`oosstorage` storage account, `oos-portfolio` container,
`ac-oos-portfolio` access connector with Storage Blob Data Contributor
on the storage account).

### 2.1 Get the notebooks into the workspace

Easiest: **Databricks Repos** (Workspace → Repos → Add Repo → paste your
GitHub URL). Pulls the whole repo and lets you re-sync after edits.

Alternative: Workspace → import the `notebooks/` folder via the UI, or
use the Databricks CLI:
```bash
databricks workspace import-dir notebooks /Workspace/Users/<you>/notebooks
```

### 2.2 Create a cluster

Compute → Create cluster:
- Runtime: **13.3 LTS or higher** (UC + Auto Loader require this)
- Access mode: **Single user** or **Shared**
- Node: smallest available is fine

Attach this cluster when running each notebook below.

### 2.3 Edit Postgres placeholders (only if you'll push to Postgres)

Edit `notebooks/config/pipeline_config.py` (bottom block) and replace
`PG_HOST`, `PG_USER`, `PG_PASSWORD` — OR preferred — create a secret
scope and the push notebook picks them up automatically:

```bash
databricks secrets create-scope oos
databricks secrets put-secret oos pg_user
databricks secrets put-secret oos pg_password
```

Skip this if you're not running step 2.10 yet.

### 2.4 Create the storage credential MANUALLY via Catalog Explorer

The credential `cred_oos_portfolio` is provisioned through the UI
(metastore-admin gated), then the rest of the SQL setup runs against it.

1. Open **Catalog Explorer** in the left nav
2. Click **External Data** → **Storage Credentials** → **Create credential**
3. Fill in:
   - **Credential type:** `Azure Managed Identity`
   - **Credential name:** `cred_oos_portfolio` *(must be exact — the
     downstream notebooks reference it by this name)*
   - **Access Connector ID:** the full Azure Resource ID — copy it from
     the Access Connector's "Properties" page in Azure Portal. Format:
     ```
     /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-oos-portfolio/providers/Microsoft.Databricks/accessConnectors/ac-oos-portfolio
     ```
4. Click **Create**.

Verify the credential exists by running just the first cell of
`notebooks/setup/01_storage_credential.sql` against your cluster — you
should see one row in `SHOW STORAGE CREDENTIALS` and a `DESCRIBE` result
with the connector ID you pasted. If `DESCRIBE` errors with "credential
not found", the name doesn't match — recreate it as `cred_oos_portfolio`.

### 2.5 Run the rest of the UC setup

Open `notebooks/setup/00_run_all_setup.py` → **Run all**.

Step 01 in the runner is verify-only (it just confirms the manual
credential from 2.4 exists). Steps 02–05 run the SQL that creates the
external location, catalog, schemas, and volume.

Expected output:
```
START storage_credential …
END   storage_credential -> ...    ← verifies cred_oos_portfolio exists
START external_location …
END   external_location -> ...
START catalog_and_schemas …
…
```
Last cell prints `UC setup complete`.

If `02_external_location` fails with a permissions error, wait 2–5 minutes
for Azure RBAC (Storage Blob Data Contributor) to propagate, then re-run
just that step. The `IF NOT EXISTS` clauses make it safe to re-run.

Verify in **Catalog Explorer**:
- Catalog `oos_portfolio` exists
- Schemas `raw`, `bronze`, `silver`, `gold` exist
- Volume `oos_portfolio.raw.landing_zone` exists

### 2.6 Upload Bucket A files to the volume

Easiest: **Catalog Explorer → oos_portfolio → raw → landing_zone → Upload**.
Drag every file from `daily_files_bucketA/` into the upload dialog.

CLI alternative (faster for hundreds of files):
```bash
for f in daily_files_bucketA/*.csv; do
  databricks fs cp "$f" "dbfs:/Volumes/oos_portfolio/raw/landing_zone/"
done
```

Verify:
```sql
LIST '/Volumes/oos_portfolio/raw/landing_zone/'
```
Should list ~303 CSV files.

### 2.7 Run the Bronze notebook

Open `notebooks/bronze/01_ingest_bronze_autoloader.py` → **Run all**
(cluster attached).

Expected exit message: `bronze rows=<N> run_date=` where N is on the order
of ~500K rows.

Verify with the Bronze SQL query from `README.md → Testing → 2`:
```sql
SELECT tbl_dt, COUNT(*) AS rows, MAX(ingested_at) AS latest_ingestion
FROM oos_portfolio.bronze.sales
GROUP BY tbl_dt ORDER BY tbl_dt DESC LIMIT 10;
```

### 2.8 Run Silver notebooks 02 → 06 in order

Run each individually (cluster attached) so you can spot-check after each:

| Notebook | Expected exit message | Verify with |
|---|---|---|
| `silver/02_compute_history` | `silver_history rows=<N>` | history SQL in Testing §2 |
| `silver/03_compute_agent_stats` | `silver_agent_stats products=~3941` | tier-distribution SQL |
| `silver/04_compute_forecast` | `silver_forecast rows=~27,500` (≈ 3941×7) | trend-factor SQL |
| `silver/05_compute_backtest` | prints `{'median_wape': …, …}` | WAPE SQL |
| `silver/06_compute_balance_snapshot` | `silver_balance products=~3941` | `SELECT COUNT(*) FROM ….oos_balance_snapshot` |

If any step fails, fix that one before moving on — every downstream step
depends on the upstream tables.

### 2.9 Run the Gold KPI notebook

Open `notebooks/gold/07_compute_kpis.py` → **Run all**.

The notebook prints a headline summary table (n_products, n_oos, oos_rate,
total_reorder_qty). Sanity values: ~3,941 products and `oos_rate` between
0.20 and 0.30.

### 2.10 (Optional) Push to PostgreSQL

Prereq: an Azure PostgreSQL Flexible Server is provisioned, the
`portfolio.oos_agent_kpi` table is created (DDL in `README.md` Day 5), and
either the secret scope from step 2.3 exists OR the placeholders in
`pipeline_config.py` have been edited.

Open `notebooks/gold/08_push_to_postgres.py` → **Run all**.

Expected exit: `push_postgres rows=~3941`.

Verify from any Postgres client (psql, DBeaver, pgAdmin):
```sql
SELECT COUNT(*), MAX(observation_date) FROM portfolio.oos_agent_kpi;
```

### 2.11 Export sample CSV for the local Streamlit demo (optional)

If you want to run the dashboard locally without Postgres, export the
gold table to a CSV from a Databricks notebook cell:

```python
(spark.table("oos_portfolio.gold.oos_agent_kpi")
      .toPandas()
      .to_csv("/Workspace/Users/<your-email>/sample_kpi.csv", index=False))
```

Then download via the Workspace UI (right-click the file → Download) and
drop it at `dashboards/sample_kpi.csv` locally. Now Part 1 step 1.4 works.

### 2.12 End-to-end smoke test (master orchestrator)

After steps 2.4–2.5 (setup) succeeded once, you don't run setup again. From
this point on, the entire daily pipeline is one notebook:

Open `notebooks/00_run_full_pipeline.py` → **Run all**.

Or from any other cell:
```python
dbutils.notebook.run(
    "./00_run_full_pipeline", 1800,
    {"run_date": "2026-05-03", "env": "dev"}
)
```

Expected: 8 `START …` / `END …` log lines, finishing with
`SUCCESS run_date=2026-05-03 env=dev`.

### 2.13 Prove incremental ingestion (Auto Loader)

This is the screenshot-worthy demo. After Bronze has run on Bucket A:

1. Upload **Bucket B** (1 file) to the same volume:
   ```bash
   databricks fs cp daily_files_bucketB/online_retail_<date>.csv \
       dbfs:/Volumes/oos_portfolio/raw/landing_zone/
   ```
2. Re-run `notebooks/bronze/01_ingest_bronze_autoloader.py`.
3. Run the SQL from `README.md → Testing → 4`. Only the new `tbl_dt`
   should have an updated `latest_ingestion`.
4. Repeat for **Bucket C** for a third proof.

If older partitions also re-ingest, the checkpoint folder
(`/Volumes/oos_portfolio/raw/landing_zone/_checkpoints/bronze_sales`)
was deleted between runs — restore it or run again to rebuild.

---

## Quick "is it working?" cheat sheet

| Symptom | Most likely cause | Fix |
|---|---|---|
| Setup notebook fails on `VALIDATE EXTERNAL LOCATION` | Azure RBAC not yet propagated | Wait 2–5 min, re-run |
| Bronze run produces 0 rows | Files not in the volume, or wrong path | `LIST '/Volumes/oos_portfolio/raw/landing_zone/'` |
| Tier distribution looks like 90/10/0 or 0/0/100 | Threshold mismatch with currency/granularity | Re-check `TIER_T*_MIN_DAILY` in `pipeline_config.py` |
| `trend_factor` is exactly 1.0 for everyone | Trend filter too aggressive (or 0-day window) | Inspect `sdf_trend` after the `.filter(isNotNull)` |
| `oos_rate` is 0% or 100% | `BALANCE_SIM_MULT_LOW/HIGH` mis-tuned | Tweak in `pipeline_config.py` |
| `08_push_to_postgres` hangs | PG firewall blocks Databricks IPs | Add Databricks workspace outbound IPs to PG firewall rules |
| Streamlit shows "Failed to load data" | Wrong env var or no CSV at path | Confirm `PG_HOST`/`OOS_CSV_PATH` |
