# Databricks notebook source
# notebooks/maintenance/reset_silver_gold.py
#
# Drops every Silver and Gold Delta table.  Bronze is untouched, so you
# can re-derive the whole downstream pipeline without re-ingesting CSVs.
# Useful when iterating on forecast / KPI logic.
#
# Safety:
#   * Defaults to DRY-RUN.  Lists what would be deleted and exits.
#   * Set the widget `confirm = YES` to actually drop.

# COMMAND ----------

# MAGIC %run ../config/pipeline_config

# COMMAND ----------

dbutils.widgets.text("confirm", "NO")
DRY_RUN = dbutils.widgets.get("confirm").strip().upper() != "YES"

TABLES = [
    T_SILVER_HISTORY,
    T_SILVER_AGENT_STATS,
    T_SILVER_FORECAST,
    T_SILVER_ACCURACY,
    T_SILVER_BALANCE,
    T_GOLD_KPI,
]

print("Mode:", "DRY-RUN (no changes)" if DRY_RUN else "EXECUTE — DROPPING")
print("Tables in scope:")
for t in TABLES:
    print(f"  {t}")

# COMMAND ----------

# Show current state.
print("\nCurrent row counts:")
for t in TABLES:
    try:
        n = spark.table(t).count()
        print(f"  {t:<48} {n:>12,} rows")
    except Exception:
        print(f"  {t:<48}      (absent)")

# COMMAND ----------

if DRY_RUN:
    print("\nDRY-RUN — no changes made.")
    print("To actually drop, set widget `confirm = YES` and re-run.")
    dbutils.notebook.exit("DRY_RUN")

# COMMAND ----------

# Drop each table.
for t in TABLES:
    print(f"Dropping {t} …")
    spark.sql(f"DROP TABLE IF EXISTS {t}")
print("All silver + gold tables dropped.")

# COMMAND ----------

# Verify.
print("\nPost-drop check:")
for t in TABLES:
    try:
        spark.table(t).count()
        print(f"  {t}  STILL EXISTS (unexpected)")
    except Exception:
        print(f"  {t}  absent ✓")

dbutils.notebook.exit("RESET_SILVER_GOLD_DONE")
