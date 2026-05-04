# Databricks notebook source
# notebooks/00_run_full_pipeline.py
# Master orchestrator — runs the full Bronze -> Silver -> Gold pipeline
# in dependency order. Each child notebook is self-contained and idempotent.

# COMMAND ----------

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# COMMAND ----------

_today = str(datetime.utcnow().date())
dbutils.widgets.text("run_date",     _today)
dbutils.widgets.text("env",          "dev")
dbutils.widgets.text("secret_scope", "oos")

run_date     = dbutils.widgets.get("run_date") or _today
env          = dbutils.widgets.get("env")
secret_scope = dbutils.widgets.get("secret_scope")

common_params = {
    "run_date":     run_date,
    "env":          env,
    "secret_scope": secret_scope,
}

# COMMAND ----------

def run_step(name: str, path: str, timeout: int = 1800, params: dict | None = None) -> str:
    print(f"START {name}  ({datetime.utcnow().isoformat()})")
    result = dbutils.notebook.run(path, timeout, params or common_params)
    print(f"END   {name}  -> {result}")
    return result

# COMMAND ----------

# STEP 1 — Bronze (Auto Loader).
run_step("bronze_autoloader", "./bronze/01_ingest_bronze_autoloader")

# STEP 2 — Silver: history first; everything downstream depends on it.
run_step("silver_history",    "./silver/02_compute_history")

# STEP 3 — agent_stats || forecast (independent of each other).
with ThreadPoolExecutor(max_workers=2) as ex:
    f_stats    = ex.submit(run_step, "silver_agent_stats", "./silver/03_compute_agent_stats")
    f_forecast = ex.submit(run_step, "silver_forecast",    "./silver/04_compute_forecast")
    f_stats.result(); f_forecast.result()

# STEP 4 — backtest depends on forecast; balance is independent.
with ThreadPoolExecutor(max_workers=2) as ex:
    f_back = ex.submit(run_step, "silver_backtest", "./silver/05_compute_backtest")
    f_bal  = ex.submit(run_step, "silver_balance",  "./silver/06_compute_balance_snapshot")
    f_back.result(); f_bal.result()

# STEP 5 — Gold KPIs (needs all silver tables).
run_step("gold_kpis", "./gold/07_compute_kpis")

# STEP 6 — Push to PostgreSQL (final serving layer).
run_step("push_postgres", "./gold/08_push_to_postgres")

# COMMAND ----------

dbutils.notebook.exit(f"SUCCESS run_date={run_date} env={env}")
