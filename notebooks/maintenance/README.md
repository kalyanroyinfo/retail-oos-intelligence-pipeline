# Maintenance notebooks

Operational reset utilities — separate from `notebooks/setup/` which
provisions the catalog, schemas, volume, storage credential, and
external location (those are one-time).

Every reset notebook **defaults to DRY-RUN**: it lists what would be
deleted and exits without touching anything. To actually wipe, set the
widget `confirm = YES` and re-run.

| Notebook | Wipes | Keeps | When to use |
|---|---|---|---|
| `reset_bronze.py` | Landing volume contents (CSVs + `_checkpoints/` + `_schemas/`) **and** the Bronze Delta table | Silver + Gold tables | Restart the Bucket A/B/C ingestion demo from scratch |
| `reset_silver_gold.py` | All Silver tables and the Gold KPI table | Bronze table, landing volume | Iterate on forecast / KPI logic without re-ingesting |
| `reset_all.py` | Everything `reset_silver_gold` + `reset_bronze` wipes (calls them in order) | Setup objects (catalog, schemas, volume, credential, external location) | Full pipeline re-run from scratch |

## Run via the UI

1. Open the notebook in Databricks
2. Edit the `confirm` widget at the top — change `NO` to `YES`
3. **Run all**

## Run programmatically

```python
dbutils.notebook.run(
    "./notebooks/maintenance/reset_bronze",
    600,
    {"confirm": "YES"},
)
```

## What's NOT reset

These notebooks intentionally don't touch:

- Storage credential (`cred_oos_portfolio`)
- External location (`ext_lakehouse`)
- Catalog (`oos_portfolio`)
- Schemas (`raw`, `bronze`, `silver`, `gold`)
- Volume object (`oos_portfolio.raw.landing_zone`)

If you need to remove those, drop them manually with `DROP CATALOG …
CASCADE` or rerun `notebooks/setup/`.
