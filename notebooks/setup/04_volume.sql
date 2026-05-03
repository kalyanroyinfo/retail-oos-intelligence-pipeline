-- Databricks notebook source
-- Step 4 / 5 — Create the external volume Auto Loader watches.
-- Depends on: 03_catalog_schemas.sql

-- COMMAND ----------

CREATE EXTERNAL VOLUME IF NOT EXISTS oos_portfolio.raw.landing_zone
  LOCATION 'abfss://oos-portfolio@oosstorage.dfs.core.windows.net/landing/uci_retail/'
  COMMENT 'Daily incoming UCI Online Retail CSV files';

-- COMMAND ----------

SHOW VOLUMES IN oos_portfolio.raw;
DESCRIBE VOLUME oos_portfolio.raw.landing_zone;

-- After this runs, files are accessible at /Volumes/oos_portfolio/raw/landing_zone/
