# Databricks notebook source
# notebooks/maintenance/reset_all.py
#
# Full pipeline-state wipe — calls reset_silver_gold then reset_bronze
# in sequence so every Delta table and the landing volume contents are
# gone.  Use only when you want to re-run the entire pipeline from
# scratch (re-upload CSVs, re-ingest Bronze, re-derive Silver, re-derive
# Gold).
#
# Setup objects (catalog, schemas, volume, storage credential, external
# location) are NOT touched — those live in notebooks/setup/ and are
# one-time provisioning.
#
# Safety:
#   * Defaults to DRY-RUN.  Forwards the same flag to both child resets.
#   * Set the widget `confirm = YES` to actually wipe.

# COMMAND ----------

dbutils.widgets.text("confirm", "NO")
confirm = dbutils.widgets.get("confirm").strip().upper()
DRY_RUN = confirm != "YES"

print("Mode:", "DRY-RUN (no changes)" if DRY_RUN else "EXECUTE — WIPING EVERYTHING")
print("Steps:")
print("  1. Drop silver + gold tables  (./reset_silver_gold)")
print("  2. Wipe landing volume + drop bronze table  (./reset_bronze)")

# COMMAND ----------

params = {"confirm": confirm}

print("\n→ Step 1 — reset_silver_gold")
result1 = dbutils.notebook.run("./reset_silver_gold", 600, params)
print(f"  → {result1}")

print("\n→ Step 2 — reset_bronze")
result2 = dbutils.notebook.run("./reset_bronze", 600, params)
print(f"  → {result2}")

# COMMAND ----------

if DRY_RUN:
    dbutils.notebook.exit("DRY_RUN — nothing changed; both child notebooks ran in dry-run mode")
else:
    dbutils.notebook.exit("RESET_ALL_DONE")
