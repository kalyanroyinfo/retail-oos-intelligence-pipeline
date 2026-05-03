# Databricks notebook source
# notebooks/silver/02_compute_history.py
# Aggregate bronze.sales to (StockCode, tbl_dt) -> daily_sales.

# COMMAND ----------

# MAGIC %run ../config/pipeline_config

# COMMAND ----------

dbutils.widgets.text("run_date", "")
dbutils.widgets.text("env", "dev")
run_date = dbutils.widgets.get("run_date")

# COMMAND ----------

from pyspark.sql import functions as F

sdf_bronze = spark.table(T_BRONZE_SALES)

sdf_history = (
    sdf_bronze
        .filter(F.col("Quantity") > 0)               # drop returns/cancellations
        .filter(F.col("UnitPrice") > 0)
        .withColumn("line_revenue", F.col("Quantity") * F.col("UnitPrice"))
        .groupBy("StockCode", "tbl_dt")
        .agg(F.sum("line_revenue").alias("daily_sales"))
)

# COMMAND ----------

(sdf_history.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(T_SILVER_HISTORY))

# COMMAND ----------

row_count = spark.table(T_SILVER_HISTORY).count()
dbutils.notebook.exit(f"silver_history rows={row_count} run_date={run_date}")
