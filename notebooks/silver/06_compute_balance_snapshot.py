# Databricks notebook source
# notebooks/silver/06_compute_balance_snapshot.py
# UCI has no real-time inventory column, so we *simulate* current_balance per product:
#   current_balance = sum(last BALANCE_SIM_LOOKBACK days sales) * U(LOW, HIGH)
# Seeded so re-runs reproduce the same balance.

# COMMAND ----------

# MAGIC %run ../config/pipeline_config

# COMMAND ----------

from datetime import datetime
_today = str(datetime.utcnow().date())
dbutils.widgets.text("run_date", _today)
dbutils.widgets.text("env", "dev")
run_date = dbutils.widgets.get("run_date") or _today

# COMMAND ----------

from pyspark.sql import functions as F

sdf_hist = spark.table(T_SILVER_HISTORY)
max_dt   = sdf_hist.agg(F.max("tbl_dt")).first()[0]
lookback_lo = F.date_sub(F.lit(max_dt), BALANCE_SIM_LOOKBACK - 1)

sdf_recent = (sdf_hist
    .filter(F.col("tbl_dt") >= lookback_lo)
    .groupBy("StockCode")
    .agg(F.sum("daily_sales").alias("recent_sum"))
)

# COMMAND ----------

sdf_balance = (sdf_recent
    .withColumn(
        "rand_mult",
        F.lit(BALANCE_SIM_MULT_LOW)
        + (F.lit(BALANCE_SIM_MULT_HIGH - BALANCE_SIM_MULT_LOW) * F.rand(seed=BALANCE_SIM_SEED)),
    )
    .withColumn("current_balance", F.col("recent_sum") * F.col("rand_mult"))
    .withColumn("observation_date", F.lit(max_dt))
    .select("StockCode", "current_balance", "observation_date")
)

# COMMAND ----------

(sdf_balance.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(T_SILVER_BALANCE))

row_count = spark.table(T_SILVER_BALANCE).count()
dbutils.notebook.exit(f"silver_balance products={row_count} run_date={run_date}")
