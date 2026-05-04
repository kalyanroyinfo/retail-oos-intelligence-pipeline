# Architecture

End-to-end Azure medallion pipeline for retail Out-of-Stock detection.

## Logical flow

```
UCI Online Retail CSV (split into ~305 daily files)
        │
        ▼
ADLS Gen2 — container: oos-portfolio
  └── landing/uci_retail/             ← daily CSV drops
        │
        ▼  (Auto Loader / cloudFiles)
Unity Catalog — catalog: oos_portfolio
  ├── raw.landing_zone        (external VOLUME → landing/uci_retail/)
  ├── bronze.sales            (Delta, partitioned by tbl_dt)
  ├── silver.oos_history
  ├── silver.agent_stats
  ├── silver.oos_forecast
  ├── silver.oos_forecast_accuracy
  ├── silver.oos_balance_snapshot
  └── gold.oos_agent_kpi
        │
        ▼  (Spark JDBC)
Azure SQL Database
  └── oos_portfolio.dbo.oos_agent_kpi
        │
        ▼
Power BI dashboard (or Streamlit alternative)
```

Orchestration: Azure Data Factory (or Databricks Workflows) calls
`notebooks/00_run_full_pipeline.py` on a daily 06:00 UTC trigger.

## Concrete Azure names (this deployment)

| Resource                   | Name                                                              |
|----------------------------|-------------------------------------------------------------------|
| Resource group             | `rg-oos-portfolio`                                                |
| Storage account            | `oosstorage`                                                      |
| Container                  | `oos-portfolio` (hyphen — Azure container rule)                   |
| Access connector           | `ac-oos-portfolio`                                                |
| Storage credential (UC)    | `cred_oos_portfolio`                                              |
| External location (UC)     | `ext_lakehouse` → `abfss://oos-portfolio@oosstorage.dfs.core.windows.net/` |
| Catalog (UC)               | `oos_portfolio` (underscore — UC convention)                      |

## Notebook tree

See `README.md → Notebook Architecture` for the full tree and what each
notebook does. In summary:

```
notebooks/
├── 00_run_full_pipeline.py        ← master orchestrator
├── setup/                         ← one-time UC provisioning
├── config/pipeline_config.py      ← shared constants
├── bronze/01_ingest_bronze_autoloader.py
├── silver/02_compute_history.py
├── silver/03_compute_agent_stats.py
├── silver/04_compute_forecast.py
├── silver/05_compute_backtest.py
├── silver/06_compute_balance_snapshot.py
├── gold/07_compute_kpis.py
├── gold/08_push_to_azure_sql.py
└── analysis/Results_and_Analysis.ipynb
```

## Execution DAG (daily ETL)

```
01_bronze_autoloader
        │
02_compute_history
   ┌────┴─────┐
   ▼          ▼
03_agent     04_compute
  _stats     _forecast
   └────┬─────┘
   ┌────┴─────┐
   ▼          ▼
05_backtest  06_balance
   └────┬─────┘
        ▼
07_compute_kpis
        │
        ▼
08_push_to_azure_sql
```

## Diagram

> TODO — replace this section with an Excalidraw export at `docs/architecture.png`.
