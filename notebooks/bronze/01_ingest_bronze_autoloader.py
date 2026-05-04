# Databricks notebook source
# notebooks/bronze/01_ingest_bronze_autoloader.py
# Auto Loader: landing CSVs -> oos_portfolio.bronze.sales (Delta, partitioned by tbl_dt)

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
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DoubleType, TimestampType,
)

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

CHECKPOINT = f"{LANDING_VOLUME}/_checkpoints/bronze_sales"
SCHEMA_LOC = f"{LANDING_VOLUME}/_schemas/bronze_sales"

# COMMAND ----------

print("CHECKPOINT LOCATION: "+CHECKPOINT)
print("SCHEMA_LOC LOCATION: "+SCHEMA_LOC)

# COMMAND ----------

bronze_stream = (
    spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.schemaLocation", SCHEMA_LOC)
        .option("header", "true")
        .schema(schema)
        .load(LANDING_VOLUME)
        .withColumn("tbl_dt",      F.to_date("InvoiceDate"))
        .withColumn("ingested_at", F.current_timestamp())
        .withColumn("source_file", F.col("_metadata.file_path"))
)

(bronze_stream.writeStream
    .format("delta")
    .option("checkpointLocation", CHECKPOINT)
    .option("mergeSchema", "true")
    .partitionBy("tbl_dt")
    .trigger(availableNow=True)         # batch-style: process all new, then exit
    .toTable(T_BRONZE_SALES))

# COMMAND ----------

row_count = spark.table(T_BRONZE_SALES).count()
dbutils.notebook.exit(f"bronze rows={row_count} run_date={run_date}")
