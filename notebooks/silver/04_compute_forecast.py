# Databricks notebook source
# notebooks/silver/04_compute_forecast.py
# Forecast = DOW_median * trend_factor * month_factor.
#  - DOW median:       per-product median daily_sales by day-of-week
#  - Trend factor:     OLS slope of daily_sales on days_ago over the last
#                      TREND_WINDOW_DAYS, projected to today and divided by
#                      overall_median (clipped per tier)
#  - Month factor:     current-month median / overall median

# COMMAND ----------

# MAGIC %run ../config/pipeline_config

# COMMAND ----------

dbutils.widgets.text("run_date", "")
dbutils.widgets.text("env", "dev")
run_date = dbutils.widgets.get("run_date")

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

sdf_hist  = spark.table(T_SILVER_HISTORY)
sdf_stats = spark.table(T_SILVER_AGENT_STATS).select("StockCode", "tier")

# Winsorize extreme daily_sales at WINSORIZE_PCT to keep medians robust.
p_cap = (
    sdf_hist
        .groupBy("StockCode")
        .agg(F.expr(f"percentile_approx(daily_sales, {WINSORIZE_PCT})").alias("p_cap"))
)
sdf_hist = (sdf_hist.join(p_cap, "StockCode", "left")
              .withColumn("daily_sales", F.least(F.col("daily_sales"), F.col("p_cap")))
              .drop("p_cap"))

# COMMAND ----------

# DOW median per product.
sdf_dow = (sdf_hist
    .withColumn("dow", F.dayofweek("tbl_dt"))                # 1=Sun .. 7=Sat
    .groupBy("StockCode", "dow")
    .agg(F.expr("percentile_approx(daily_sales, 0.5)").alias("dow_median"))
)

# Overall median per product (denominator for trend + month factor).
# Median is more robust than mean against UCI's heavy right tail.
sdf_overall = (sdf_hist
    .groupBy("StockCode")
    .agg(F.expr("percentile_approx(daily_sales, 0.5)").alias("overall_median"))
)

# Trend factor — OLS regression of daily_sales on days_ago over the last
# TREND_WINDOW_DAYS, then project to today.
#   days_ago        = datediff(max_dt, tbl_dt)        # 0 today, larger = older
#   trend_slope     = covar_pop(days_ago, daily_sales) / var_pop(days_ago)
#   projected_today = trend_avg − slope × avg(days_ago)
# A POSITIVE slope means older days had higher sales (declining trend),
# so the projection at days_ago=0 (today) lifts/lowers correctly via the
# OLS intercept.  Using the *actual* avg(days_ago) — not window/2 —
# matters for sparse products that only sell on a handful of days in the
# window.  Products with <2 distinct active days have var_pop=0, so the
# slope is NULL; filter them out and they fall back to trend_factor=1.0
# via the coalesce on the join below.
max_dt = sdf_hist.agg(F.max("tbl_dt")).first()[0]
sdf_trend = (sdf_hist
    .filter(F.col("tbl_dt") >= F.date_sub(F.lit(max_dt), TREND_WINDOW_DAYS))
    .withColumn("days_ago", F.datediff(F.lit(max_dt), F.col("tbl_dt")).cast("double"))
    .groupBy("StockCode")
    .agg(
        F.avg("daily_sales").alias("trend_avg"),
        F.avg("days_ago").alias("avg_days_ago"),
        F.expr("covar_pop(days_ago, daily_sales) / var_pop(days_ago)").alias("trend_slope"),
    )
    .filter(F.col("trend_slope").isNotNull())
    .withColumn(
        "projected_today",
        F.col("trend_avg") - F.col("trend_slope") * F.col("avg_days_ago"),
    )
    .select("StockCode", "projected_today")
)

# Month factor: current-month median / overall median.
current_month = max_dt.month if max_dt is not None else None
sdf_month = (sdf_hist
    .filter(F.month("tbl_dt") == F.lit(current_month))
    .groupBy("StockCode")
    .agg(F.expr("percentile_approx(daily_sales, 0.5)").alias("month_median"))
)

# COMMAND ----------

# Cross-join DOW (1..7) per product so every product has 7 forecast rows.
dows = spark.range(1, 8).toDF("dow")
sdf_grid = sdf_stats.crossJoin(dows)                         # (StockCode, tier, dow)

sdf_forecast = (sdf_grid
    .join(sdf_dow,     ["StockCode", "dow"], "left")
    .join(sdf_overall, "StockCode", "left")
    .join(sdf_trend,   "StockCode", "left")
    .join(sdf_month,   "StockCode", "left")
    .withColumn(
        "trend_raw",
        F.when(
            (F.col("overall_median") > 0) & F.col("projected_today").isNotNull(),
            F.col("projected_today") / F.col("overall_median"),
        ).otherwise(F.lit(1.0)),
    )
    .withColumn(
        "month_factor",
        F.when(F.col("overall_median") > 0, F.col("month_median") / F.col("overall_median"))
         .otherwise(F.lit(1.0)),
    )
)

# Per-tier clip on the trend factor.
sdf_forecast = (sdf_forecast
    .withColumn("clip_lo",
        F.when(F.col("tier") == "T1", F.lit(SCALE_CLIP_T1[0]))
         .when(F.col("tier") == "T2", F.lit(SCALE_CLIP_T2[0]))
         .otherwise(F.lit(SCALE_CLIP_T3[0])))
    .withColumn("clip_hi",
        F.when(F.col("tier") == "T1", F.lit(SCALE_CLIP_T1[1]))
         .when(F.col("tier") == "T2", F.lit(SCALE_CLIP_T2[1]))
         .otherwise(F.lit(SCALE_CLIP_T3[1])))
    .withColumn("trend_factor", F.greatest(F.col("clip_lo"),
                                F.least(F.col("clip_hi"), F.col("trend_raw"))))
    .withColumn("forecast",
        F.greatest(F.lit(0.0),
                   F.coalesce(F.col("dow_median"), F.col("overall_median"), F.lit(0.0))
                   * F.coalesce(F.col("trend_factor"), F.lit(1.0))
                   * F.coalesce(F.col("month_factor"), F.lit(1.0))))
    .select("StockCode", "tier", "dow", "dow_median",
            "trend_factor", "month_factor", "forecast")
)

# COMMAND ----------

(sdf_forecast.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(T_SILVER_FORECAST))

# COMMAND ----------

row_count = spark.table(T_SILVER_FORECAST).count()
dbutils.notebook.exit(f"silver_forecast rows={row_count} run_date={run_date}")
