-- Databricks notebook source
-- Step 5 / 5 — (Optional) grants for a multi-user demo.
-- Skip for a solo-user portfolio account.

-- COMMAND ----------

-- External-location grants (allow non-admins to create tables under it).
GRANT CREATE EXTERNAL TABLE  ON EXTERNAL LOCATION ext_lakehouse TO `account users`;
GRANT CREATE MANAGED STORAGE ON EXTERNAL LOCATION ext_lakehouse TO `account users`;
GRANT READ FILES             ON EXTERNAL LOCATION ext_lakehouse TO `account users`;
GRANT WRITE FILES            ON EXTERNAL LOCATION ext_lakehouse TO `account users`;

-- COMMAND ----------

-- Catalog / schema usage + read on the gold layer.
GRANT USE CATALOG  ON CATALOG oos_portfolio              TO `account users`;
GRANT USE SCHEMA   ON SCHEMA  oos_portfolio.bronze       TO `account users`;
GRANT USE SCHEMA   ON SCHEMA  oos_portfolio.silver       TO `account users`;
GRANT USE SCHEMA   ON SCHEMA  oos_portfolio.gold         TO `account users`;
GRANT SELECT       ON SCHEMA  oos_portfolio.gold         TO `account users`;
GRANT READ VOLUME  ON VOLUME  oos_portfolio.raw.landing_zone TO `account users`;
