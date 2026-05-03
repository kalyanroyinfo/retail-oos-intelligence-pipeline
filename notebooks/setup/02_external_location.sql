-- Databricks notebook source
-- Step 2 / 5 — Register the oos-portfolio container as an external location.
-- Privilege required: METASTORE ADMIN
-- Depends on: 01_storage_credential.sql

-- COMMAND ----------

CREATE EXTERNAL LOCATION IF NOT EXISTS ext_lakehouse
  URL 'abfss://oos-portfolio@oosstorage.dfs.core.windows.net/'
  WITH (STORAGE CREDENTIAL cred_oos_portfolio)
  COMMENT 'Root external location for OOS lakehouse (covers landing/, bronze/, silver/, gold/)';

-- COMMAND ----------

-- Equivalent to clicking "Test connection" in the UI.
-- If this fails with a permissions error, wait 2-5 minutes for RBAC to propagate then re-run.
VALIDATE EXTERNAL LOCATION ext_lakehouse;

-- COMMAND ----------

SHOW EXTERNAL LOCATIONS;
DESCRIBE EXTERNAL LOCATION ext_lakehouse;
