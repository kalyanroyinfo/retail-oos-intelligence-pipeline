# Databricks notebook source
# notebooks/gold/07_compute_kpis.py
# Final OOS KPIs: join balance + forecast + accuracy + agent_stats,
# apply bias correction, compute is_oos / reorder_qty / balance_color.

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

# Use today's DOW to pick the right forecast row per product.
sdf_forecast_today = (spark.table(T_SILVER_FORECAST)
    .withColumn("dow_today", F.dayofweek(F.current_date()))
    .filter(F.col("dow") == F.col("dow_today"))
    .select("StockCode", F.col("forecast").alias("forecast"))
)

sdf_balance  = spark.table(T_SILVER_BALANCE)
sdf_accuracy = spark.table(T_SILVER_ACCURACY).select("StockCode", "wape", "bias_correction")
sdf_stats    = spark.table(T_SILVER_AGENT_STATS).select("StockCode", "tier")

# Country comes from the bronze table — pick the most-recent country per product.
# Normalise StockCode the same way silver/02 does, otherwise bronze's raw
# whitespace/case variants produce two country rows for what the silver
# layer treats as one product, and the join below blows up by a factor.
sdf_country = (spark.table(T_BRONZE_SALES)
    .withColumn("StockCode", F.upper(F.trim(F.col("StockCode"))))
    .filter(F.col("StockCode") != "")
    .groupBy("StockCode")
    .agg(F.last("Country", ignorenulls=True).alias("country"))
)

# COMMAND ----------

sdf = (sdf_balance
    .join(sdf_forecast_today, "StockCode", "left")
    .join(sdf_accuracy,       "StockCode", "left")
    .join(sdf_stats,          "StockCode", "left")
    .join(sdf_country,        "StockCode", "left")
    .withColumn("forecast",         F.coalesce(F.col("forecast"),        F.lit(0.0)))
    .withColumn("bias_correction",  F.coalesce(F.col("bias_correction"), F.lit(1.0)))
    .withColumn("corrected_forecast", F.col("forecast") * F.col("bias_correction"))
    .withColumn(
        "oos_threshold",
        F.greatest(
            F.lit(float(OOS_THRESHOLD_FLOOR)),
            F.col("corrected_forecast") * F.lit(float(OOS_THRESHOLD_DAYS)),
        ),
    )
    .withColumn("is_oos", F.col("current_balance") < F.col("oos_threshold"))
    .withColumn(
        "reorder_qty",
        F.ceil(F.greatest(
            F.lit(0.0),
            F.col("corrected_forecast") * F.lit(float(TOPUP_BUFFER_DAYS)) - F.col("current_balance"),
        )),
    )
    .withColumn(
        "balance_color",
        F.when(F.col("current_balance") >= F.lit(float(BALANCE_GREEN_MIN)), F.lit("GREEN"))
         .when(F.col("current_balance") >= F.lit(float(BALANCE_AMBER_MIN)), F.lit("AMBER"))
         .otherwise(F.lit("RED")),
    )
    .select(
        F.col("StockCode").alias("stock_code"),
        F.col("country"),
        F.col("tier"),
        F.col("current_balance"),
        F.col("corrected_forecast"),
        F.col("oos_threshold"),
        F.col("is_oos"),
        F.col("reorder_qty"),
        F.col("balance_color"),
        F.col("wape"),
        F.col("observation_date"),
    )
)

# COMMAND ----------

(sdf.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(T_GOLD_KPI))

# Headline KPIs.
display(spark.sql(f"""
  SELECT
    COUNT(*)                                         AS n_products,
    SUM(CASE WHEN is_oos THEN 1 ELSE 0 END)          AS n_oos,
    ROUND(AVG(CASE WHEN is_oos THEN 1.0 ELSE 0.0 END), 3) AS oos_rate,
    SUM(reorder_qty)                              AS total_reorder_qty
  FROM {T_GOLD_KPI}
"""))

row_count = spark.table(T_GOLD_KPI).count()
dbutils.notebook.exit(f"gold_kpis products={row_count} run_date={run_date}")
