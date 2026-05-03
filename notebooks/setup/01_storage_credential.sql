-- Databricks notebook source
-- Step 1 / 5 — Storage credential.
--
-- ⚠️  This step is performed **manually** in the Databricks Catalog
--     Explorer UI, NOT via SQL.  The notebook only verifies that the
--     credential exists with the expected name afterwards.
--
-- ── Manual UI steps (one-time, metastore admin) ───────────────────────
--   1. Catalog Explorer  →  External Data  →  Storage Credentials  →  Create
--   2. Type:                Azure Managed Identity
--      Name:                cred_oos_portfolio       ← MUST match exactly
--      Access Connector ID: copy the full Azure Resource ID from the
--                           Access Connector "Properties" page, e.g.
--      /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-oos-portfolio/providers/Microsoft.Databricks/accessConnectors/ac-oos-portfolio
--   3. Click Create.
--
-- The downstream notebooks (02_external_location.sql etc.) reference
-- this credential by name, so they run unchanged as long as the name is
-- exactly `cred_oos_portfolio`.

-- COMMAND ----------

-- Verification.  DESCRIBE will raise an error if the credential is
-- missing, which fails the master setup runner fast and surfaces the
-- "you forgot to create it in the UI" case immediately.
SHOW STORAGE CREDENTIALS;
DESCRIBE STORAGE CREDENTIAL cred_oos_portfolio;
