# Databricks notebook source
# notebooks/setup/00_run_all_setup.py
# One-time UC setup runner — calls 5 SQL/Python steps in dependency order.
# Idempotent: every step uses CREATE ... IF NOT EXISTS.

# COMMAND ----------

from datetime import datetime


def run_step(name: str, path: str, timeout: int = 600) -> str:
    print(f"START {name}  ({datetime.utcnow().isoformat()})")
    result = dbutils.notebook.run(path, timeout)
    print(f"END   {name}  -> {result}")
    return result

# COMMAND ----------

# Strict dependency chain — DO NOT reorder.
# NOTE: step 01 is verify-only — the storage credential is created
# manually via the Catalog Explorer UI (see 01_storage_credential.sql
# header).  This step fast-fails if the credential is missing.
try:
    run_step("storage_credential",  "./01_storage_credential")    # verify
    run_step("external_location",   "./02_external_location")     # admin (depends on #1)
    run_step("catalog_and_schemas", "./03_catalog_schemas")        # depends on #2
    run_step("landing_volume",      "./04_volume")                 # depends on #3
    #run_step("grants",              "./05_grants")                 # optional
except Exception as e:
    error_msg = str(e)
    print(f"\n❌ Setup failed. Check the error above for details.")
    print(f"\nCommon causes:")
    print(f"  • Storage credential 'cred_oos_portfolio' not created in UI yet")
    print(f"  • Missing METASTORE ADMIN privileges")
    print(f"  • RBAC permissions still propagating (wait 2-5 minutes)")
    raise

# COMMAND ----------

dbutils.notebook.exit("UC setup complete")
