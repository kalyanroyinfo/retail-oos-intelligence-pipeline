# Databricks notebook source
# notebooks/config/pipeline_config.py
# Calibrated for UCI Online Retail (GBP, daily granularity, ~3,941 products).
# Imported into every ETL notebook via:  %run ../config/pipeline_config

# COMMAND ----------

# ── Unity Catalog object names ───────────────────────────────────
CATALOG = "oos_portfolio"
RAW_SCHEMA    = f"{CATALOG}.raw"
BRONZE_SCHEMA = f"{CATALOG}.bronze"
SILVER_SCHEMA = f"{CATALOG}.silver"
GOLD_SCHEMA   = f"{CATALOG}.gold"

# Volume path (Auto Loader watches this)
LANDING_VOLUME = f"/Volumes/{CATALOG}/raw/landing_zone"

# COMMAND ----------

# ── Fully-qualified table names ──────────────────────────────────
T_BRONZE_SALES        = f"{BRONZE_SCHEMA}.sales"
T_SILVER_HISTORY      = f"{SILVER_SCHEMA}.oos_history"
T_SILVER_AGENT_STATS  = f"{SILVER_SCHEMA}.agent_stats"
T_SILVER_FORECAST     = f"{SILVER_SCHEMA}.oos_forecast"
T_SILVER_ACCURACY     = f"{SILVER_SCHEMA}.oos_forecast_accuracy"
T_SILVER_BALANCE      = f"{SILVER_SCHEMA}.oos_balance_snapshot"
T_GOLD_KPI            = f"{GOLD_SCHEMA}.oos_agent_kpi"

# COMMAND ----------

# ── OOS thresholds ───────────────────────────────────────────────
# Calibrated against UCI percentiles: median £14.22, p25 £7.50, p75 £26.86, p95 £79
OOS_THRESHOLD_FLOOR     = 5      # £ floor — ≈ p25 daily sales
OOS_THRESHOLD_DAYS      = 1.0    # threshold = max(floor, forecast × this)
TOPUP_BUFFER_DAYS       = 2.0    # restock target covers this many forecast days

# COMMAND ----------

# ── Product tiers (DAILY revenue) ────────────────────────────────
TIER_T1_MIN_DAILY       = 30     # £/day → ~22% T1
TIER_T2_MIN_DAILY       = 8      # £/day → ~38% T2  (T3 = remainder ~40%)

# Forecast scale-factor clip per tier
SCALE_CLIP_T1           = (0.5, 5.0)   # T1: most volatile, widest clip
SCALE_CLIP_T2           = (0.5, 3.0)
SCALE_CLIP_T3           = (0.5, 1.5)   # T3: tight clip (low-volume noise)

# COMMAND ----------

# ── Outlier handling ─────────────────────────────────────────────
WINSORIZE_PCT           = 0.95   # p95 cap on extreme daily sales
BIAS_CORRECTION_CLIP    = (0.5, 3.0)

# ── Backtest ─────────────────────────────────────────────────────
BACKTEST_DAYS           = 7
TREND_WINDOW_DAYS       = 45     # UCI dataset is ~305 days; OK
COLD_START_DAYS         = 7
COLD_START_BUFFER       = 1.1

# ── Balance simulation (UCI has no real inventory data) ──────────
BALANCE_SIM_LOOKBACK    = 3
BALANCE_SIM_MULT_LOW    = 0.3
BALANCE_SIM_MULT_HIGH   = 1.5    # → ~25% OOS rate
BALANCE_SIM_SEED        = 42

# ── Balance-color bands (Day 5 KPI step) ─────────────────────────
BALANCE_GREEN_MIN       = 80     # £
BALANCE_AMBER_MIN       = 25     # £

# ── Currency / display ───────────────────────────────────────────
CURRENCY_SYMBOL         = "£"
CURRENCY_CODE           = "GBP"

# ── PostgreSQL serving layer (override via Databricks secret scope) ──
# Keep placeholders here — real values come from a secret scope at runtime.
PG_HOST     = "REPLACE_ME.postgres.database.azure.com"
PG_DB       = "postgres"
PG_TABLE    = "portfolio.oos_agent_kpi"
PG_USER     = "REPLACE_ME"          # prefer dbutils.secrets.get(...)
PG_PASSWORD = "REPLACE_ME"          # prefer dbutils.secrets.get(...)
