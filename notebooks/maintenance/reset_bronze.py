# Databricks notebook source
# notebooks/maintenance/reset_bronze.py
#
# Wipes the landing-volume contents (CSVs + Auto Loader checkpoint +
# schema cache) AND drops the Bronze Delta table.  Use to restart the
# Bucket A/B/C ingestion demo from a clean slate.
#
# Safety:
#   * Defaults to DRY-RUN.  Lists what would be deleted and exits.
#   * Set the widget `confirm = YES` to actually wipe.

# COMMAND ----------

# MAGIC %run ../config/pipeline_config

# COMMAND ----------

dbutils.widgets.text("confirm", "NO")
DRY_RUN = dbutils.widgets.get("confirm").strip().upper() != "YES"

print("Mode:           ", "DRY-RUN (no changes)" if DRY_RUN else "EXECUTE — DELETING")
print("Landing volume: ", LANDING_VOLUME)
print("Bronze table:   ", T_BRONZE_SALES)

# COMMAND ----------

# Show current state.
try:
    entries = dbutils.fs.ls(LANDING_VOLUME)
    print(f"\nVolume contents ({len(entries)} entries):")
    for f in entries[:10]:
        kind = "DIR" if f.isDir() else f"{f.size:,} B"
        print(f"  {kind:>12}  {f.path}")
    if len(entries) > 10:
        print(f"  … ({len(entries) - 10} more not shown)")
except Exception as exc:
    print(f"\nVolume listing failed: {exc}")

try:
    n = spark.table(T_BRONZE_SALES).count()
    print(f"\nBronze table row count: {n:,}")
except Exception as exc:
    print(f"\nBronze table not present: {exc}")

# COMMAND ----------

if DRY_RUN:
    print("\nDRY-RUN — no changes made.")
    print("To actually wipe, set widget `confirm = YES` and re-run.")
    dbutils.notebook.exit("DRY_RUN")

# COMMAND ----------

# 1. Wipe the children of the volume root (CSVs + _checkpoints + _schemas).
#    We delete children rather than the volume root itself so the volume
#    object stays usable without recreation.
print(f"Wiping contents of {LANDING_VOLUME} …")
removed = 0
for entry in dbutils.fs.ls(LANDING_VOLUME):
    dbutils.fs.rm(entry.path, recurse=True)
    removed += 1
print(f"Removed {removed} entries.")

# COMMAND ----------

# 2. Drop the Bronze Delta table.
print(f"Dropping {T_BRONZE_SALES} …")
spark.sql(f"DROP TABLE IF EXISTS {T_BRONZE_SALES}")
print("Done.")

# COMMAND ----------

# Verify.
try:
    after = dbutils.fs.ls(LANDING_VOLUME)
    print(f"Volume now contains: {len(after)} entries")
except Exception as exc:
    print(f"Volume listing: {exc}  (root may be empty)")

try:
    spark.table(T_BRONZE_SALES).count()
    print("UNEXPECTED: bronze table still readable.")
except Exception:
    print("Bronze table confirmed absent.")

dbutils.notebook.exit("RESET_BRONZE_DONE")
