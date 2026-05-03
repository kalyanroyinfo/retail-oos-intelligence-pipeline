# Databricks notebook source
# notebooks/silver/05_compute_backtest.py
# Walk-forward backtest over the last BACKTEST_DAYS days.
# For each held-out day, predict using DOW median computed from prior data only,
# then compute per-product WAPE and bias_correction (clipped).

# COMMAND ----------

# MAGIC %run ../config/pipeline_config

# COMMAND ----------

dbutils.widgets.text("run_date", "")
dbutils.widgets.text("env", "dev")
run_date = dbutils.widgets.get("run_date")

# COMMAND ----------

from pyspark.sql import functions as F

sdf_hist = spark.table(T_SILVER_HISTORY)

max_dt    = sdf_hist.agg(F.max("tbl_dt")).first()[0]
holdout_lo = F.date_sub(F.lit(max_dt), BACKTEST_DAYS - 1)
sdf_train  = sdf_hist.filter(F.col("tbl_dt") <  holdout_lo)
sdf_test   = sdf_hist.filter(F.col("tbl_dt") >= holdout_lo)

# COMMAND ----------

# DOW median computed only from training data.
sdf_train_dow = (sdf_train
    .withColumn("dow", F.dayofweek("tbl_dt"))
    .groupBy("StockCode", "dow")
    .agg(F.expr("percentile_approx(daily_sales, 0.5)").alias("forecast"))
)

sdf_pred = (sdf_test
    .withColumn("dow", F.dayofweek("tbl_dt"))
    .join(sdf_train_dow, ["StockCode", "dow"], "left")
    .withColumnRenamed("daily_sales", "actual")
    .withColumn("forecast", F.coalesce(F.col("forecast"), F.lit(0.0)))
    .withColumn("abs_err",  F.abs(F.col("actual") - F.col("forecast")))
)

# COMMAND ----------

sdf_accuracy = (sdf_pred
    .groupBy("StockCode")
    .agg(
        F.sum("abs_err").alias("sum_abs_err"),
        F.sum("actual").alias("sum_actual"),
        F.sum("forecast").alias("sum_forecast"),
        F.count(F.lit(1)).alias("test_days"),
    )
    .withColumn(
        "wape",
        F.when(F.col("sum_actual") > 0, F.col("sum_abs_err") / F.col("sum_actual"))
         .otherwise(F.lit(None).cast("double")),
    )
    .withColumn(
        "bias_raw",
        F.when(F.col("sum_forecast") > 0, F.col("sum_actual") / F.col("sum_forecast"))
         .otherwise(F.lit(1.0)),
    )
    .withColumn(
        "bias_correction",
        F.greatest(F.lit(BIAS_CORRECTION_CLIP[0]),
                   F.least(F.lit(BIAS_CORRECTION_CLIP[1]), F.col("bias_raw"))),
    )
)

# COMMAND ----------

(sdf_accuracy.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(T_SILVER_ACCURACY))

# COMMAND ----------

# Print headline metrics for the README write-up.
metrics = (spark.table(T_SILVER_ACCURACY)
    .agg(
        F.expr("percentile_approx(wape, 0.5)").alias("median_wape"),
        F.avg((F.col("wape") < 0.5).cast("int")).alias("pct_wape_under_50"),
        F.count(F.lit(1)).alias("n_products"),
    )
).first().asDict()
print(metrics)

dbutils.notebook.exit(f"silver_backtest products={metrics['n_products']} run_date={run_date}")
