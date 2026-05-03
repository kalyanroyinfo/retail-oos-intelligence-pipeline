-- Databricks notebook source
-- Step 3 / 5 — Create the catalog and the four medallion schemas, each with its own
-- managed-location sub-folder under the oos-portfolio container.
-- Depends on: 02_external_location.sql

-- COMMAND ----------

CREATE CATALOG IF NOT EXISTS oos_portfolio
  COMMENT 'Portfolio project: retail OOS detection pipeline (medallion architecture)';

USE CATALOG oos_portfolio;

-- COMMAND ----------

CREATE SCHEMA IF NOT EXISTS oos_portfolio.raw
  MANAGED LOCATION 'abfss://oos-portfolio@oosstorage.dfs.core.windows.net/landing/'
  COMMENT 'Landing zone: raw incoming files via Auto Loader';

CREATE SCHEMA IF NOT EXISTS oos_portfolio.bronze
  MANAGED LOCATION 'abfss://oos-portfolio@oosstorage.dfs.core.windows.net/bronze/'
  COMMENT 'Bronze layer: ingested raw Delta tables';

CREATE SCHEMA IF NOT EXISTS oos_portfolio.silver
  MANAGED LOCATION 'abfss://oos-portfolio@oosstorage.dfs.core.windows.net/silver/'
  COMMENT 'Silver layer: cleaned + feature-engineered tables';

CREATE SCHEMA IF NOT EXISTS oos_portfolio.gold
  MANAGED LOCATION 'abfss://oos-portfolio@oosstorage.dfs.core.windows.net/gold/'
  COMMENT 'Gold layer: business KPI tables';

-- COMMAND ----------

SHOW CATALOGS;
SHOW SCHEMAS IN oos_portfolio;
DESCRIBE SCHEMA EXTENDED oos_portfolio.bronze;
