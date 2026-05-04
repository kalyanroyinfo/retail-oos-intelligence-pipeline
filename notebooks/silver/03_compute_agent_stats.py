# Databricks notebook source
# notebooks/silver/03_compute_agent_stats.py
# Tier classification using avg daily sales (£): T1 >= TIER_T1_MIN_DAILY,
# T2 >= TIER_T2_MIN_DAILY, T3 = remainder.

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

sdf_history = spark.table(T_SILVER_HISTORY)

sdf_stats = (
    sdf_history
        .groupBy("StockCode")
        .agg(
            F.avg("daily_sales").alias("avg_daily_sales"),
            F.expr("percentile_approx(daily_sales, 0.5)").alias("median_daily_sales"),
            F.stddev("daily_sales").alias("stddev_daily_sales"),
            F.min("tbl_dt").alias("first_seen_dt"),
            F.max("tbl_dt").alias("last_seen_dt"),
            F.count(F.lit(1)).alias("active_days"),
        )
        .withColumn(
            "tier",
            F.when(F.col("avg_daily_sales") >= TIER_T1_MIN_DAILY, F.lit("T1"))
             .when(F.col("avg_daily_sales") >= TIER_T2_MIN_DAILY, F.lit("T2"))
             .otherwise(F.lit("T3")),
        )
)

# COMMAND ----------

(sdf_stats.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(T_SILVER_AGENT_STATS))

# COMMAND ----------

# Sanity: tier distribution should be roughly 22 / 38 / 40.
display(
    spark.table(T_SILVER_AGENT_STATS)
         .groupBy("tier")
         .count()
         .orderBy("tier")
)

row_count = spark.table(T_SILVER_AGENT_STATS).count()
dbutils.notebook.exit(f"silver_agent_stats products={row_count} run_date={run_date}")
