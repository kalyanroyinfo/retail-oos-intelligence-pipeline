-- Databricks notebook source
-- Step 1 / 5 — Create UC storage credential bound to the Access Connector managed identity.
-- Privilege required: METASTORE ADMIN
--
-- Replace <SUBSCRIPTION_ID> with your Azure subscription id before running.

-- COMMAND ----------

CREATE STORAGE CREDENTIAL IF NOT EXISTS cred_oos_portfolio
  WITH AZURE_MANAGED_IDENTITY
       '/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-oos-portfolio/providers/Microsoft.Databricks/accessConnectors/ac-oos-portfolio'
  COMMENT 'Managed identity used by UC to access the oos-portfolio container';

-- COMMAND ----------

SHOW STORAGE CREDENTIALS;
DESCRIBE STORAGE CREDENTIAL cred_oos_portfolio;
