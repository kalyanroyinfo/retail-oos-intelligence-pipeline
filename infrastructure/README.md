# Azure Infrastructure — Manual Setup Guide

Step-by-step Portal walkthrough for provisioning every Azure resource the
pipeline depends on.  Run once per environment.

> All resources go in the same region (e.g. `East US`) so intra-region
> traffic stays free.  Pick your region in Step 1 and stick with it.

## End state at a glance

| # | Resource | Name | Purpose |
|---|---|---|---|
| 1 | Resource Group | `rg-oos-portfolio` | Container for everything below |
| 2 | Access Connector for Azure Databricks | `ac-oos-portfolio` | Managed-identity bridge UC ↔ Storage |
| 3 | Storage Account (ADLS Gen 2) | `oosstorage` | Lakehouse storage |
| 3a | Container | `oos-portfolio` | Inside the storage account |
| 4 | RBAC role assignment | — | `Storage Blob Data Contributor` on storage, member = AC |
| 5 | Azure Databricks Workspace | `dbw-oos-portfolio` | **Premium tier** (UC + Auto Loader require it) |
| 6 | Databricks SQL Warehouse / Cluster | — | Compute |
| 7 | Storage Credential (UC) | `cred_oos_portfolio` | UC's pointer to the AC |
| 8 | External Location (UC) | `ext_lakehouse` | UC's view of the container |
| 9 | Catalog + schemas + volume | `oos_portfolio` etc. | Created via `notebooks/setup/` |
| 10 | Azure SQL Database (serving) | `oos-sql-server` / `oos_portfolio` | Where gold KPIs land |

---

## Prerequisites

- An active Azure subscription with Contributor (or higher) on the subscription/resource group.
- Sign in at <https://portal.azure.com>.
- Pick a region you'll use for everything (e.g. `East US`).

---

## Step 1 — Create the Resource Group

Portal → top search → **"Resource groups"** → **+ Create**.

| Field | Value |
|---|---|
| Subscription | yours |
| Resource group name | `rg-oos-portfolio` |
| Region | e.g. `East US` (note this — every resource below uses the same) |

**Review + create** → **Create**.

✅ Verify: search "Resource groups" → see `rg-oos-portfolio`.

---

## Step 2 — Create the Access Connector for Azure Databricks

Lets Unity Catalog reach storage via a managed identity (no keys, no secrets).

Portal → top search → **"Access Connector for Azure Databricks"** → **+ Create**.

| Field | Value |
|---|---|
| Subscription | yours |
| Resource group | `rg-oos-portfolio` |
| Name | `ac-oos-portfolio` |
| Region | same as RG |
| Identity type | **System assigned** *(default)* |

**Review + create** → **Create**.

After deployment → **Go to resource** → **Properties** (left nav) → copy the **Resource ID**:

```
/subscriptions/<sub-id>/resourceGroups/rg-oos-portfolio/providers/Microsoft.Databricks/accessConnectors/ac-oos-portfolio
```

⚠️ **Save this string** — you'll paste it into Step 7.

---

## Step 3 — Create the Storage Account (ADLS Gen 2)

Portal → top search → **"Storage accounts"** → **+ Create**.

**Basics tab:**

| Field | Value |
|---|---|
| Resource group | `rg-oos-portfolio` |
| Storage account name | `oosstorage` *(globally unique, lowercase 3–24 chars; add suffix if taken)* |
| Region | same as RG |
| Performance | **Standard** |
| Redundancy | **Locally-redundant storage (LRS)** *(cheapest)* |

**Advanced tab:**

| Field | Value |
|---|---|
| **Enable hierarchical namespace** | ✅ **Tick this** — this is the ADLS Gen 2 switch |
| Minimum TLS version | 1.2 *(default)* |

**Networking tab:** leave defaults (public endpoint, all networks).
**Data protection tab:** leave defaults.

**Review + create** → **Create**.

### Step 3a — Create the container

After the storage account deploys → **Go to resource** → **Containers** (left nav) → **+ Container**.

| Field | Value |
|---|---|
| Name | `oos-portfolio` *(must be lowercase + hyphens — no underscores)* |
| Public access level | **Private (no anonymous access)** |

**Create**.

✅ Verify: container `oos-portfolio` shows in the Containers list.

> 📝 **Naming gotcha** — Azure container names disallow underscores, so it's `oos-portfolio` (hyphen). The Unity Catalog name later is `oos_portfolio` (underscore — UC convention).

---

## Step 4 — Grant the Access Connector access to storage

This RBAC link is what makes Step 7's storage credential validate.

Portal → your storage account `oosstorage` → **Access Control (IAM)** (left nav) → **+ Add** → **Add role assignment**.

**Role tab:**

| Field | Value |
|---|---|
| Search | **Storage Blob Data Contributor** |

Click the row → **Next**.

**Members tab:**

| Field | Value |
|---|---|
| Assign access to | **Managed identity** |
| Members | click **+ Select members** |

In the side panel:

| Field | Value |
|---|---|
| Subscription | yours |
| Managed identity (dropdown) | **Access connector for Azure Databricks** |
| Pick | `ac-oos-portfolio` |

**Select** → **Next** → **Review + assign** → **Review + assign**.

⚠️ **Wait 2–5 minutes for the RBAC to propagate** before doing Step 8. Skipping this wait is the #1 cause of `VALIDATE EXTERNAL LOCATION` failures.

---

## Step 5 — Create the Azure Databricks Workspace

⚠️ **Premium tier is required** — Unity Catalog and Auto Loader will not work on Standard.

Portal → top search → **"Azure Databricks"** → **+ Create**.

| Field | Value |
|---|---|
| Resource group | `rg-oos-portfolio` |
| Workspace name | `dbw-oos-portfolio` |
| Region | same as RG |
| Pricing tier | **Premium (+ Role-based access controls)** |
| Managed Resource Group name | leave blank *(auto-generated)* |

**Networking tab:** leave defaults (public, no VNet injection).
**Encryption tab:** leave defaults.
**Tags:** optional.

**Review + create** → **Create**. Provisioning takes 5–8 minutes.

After deployment → **Go to resource** → **Launch Workspace**. The Databricks UI opens in a new tab.

---

## Step 6 — Create a cluster (and optionally a SQL warehouse)

### Cluster (for ETL notebooks)

Inside Databricks → **Compute** (left nav) → **Create cluster**.

| Field | Value |
|---|---|
| Cluster name | `oos-cluster` |
| Cluster mode | **Single user** *(or Shared — both UC-enabled)* |
| Databricks runtime | **13.3 LTS or later** *(UC requires this)* |
| Node type | smallest available, e.g. `Standard_DS3_v2` |
| Min/Max workers | 1 / 1 |
| Auto-stop | **30 min** |

**Create**. Wait until status is **Running**.

### SQL Warehouse (optional — only if you build a Databricks SQL dashboard)

Skip this if you're staying with Azure SQL Database as the only serving target. Otherwise:

**SQL Warehouses** → **Create SQL warehouse** → cluster size **2X-Small**, auto-stop **5 min** → **Create**.

---

## Step 7 — Create the Storage Credential (UC ↔ AC link)

Inside Databricks Workspace:

1. **Catalog** (left nav) → **External Data** → **Storage Credentials** tab
   *(or on newer UI: ⚙ Settings → External Locations → Credentials tab)*
2. **Create credential**:

   | Field | Value |
   |---|---|
   | Credential type | **Azure Managed Identity** |
   | Credential name | `cred_oos_portfolio` *(must match `notebooks/setup/02_external_location.sql`)* |
   | Access Connector ID | paste the **Resource ID** from Step 2 |

3. Click **Create**.

✅ Verify by running in any SQL cell:
```sql
DESCRIBE STORAGE CREDENTIAL cred_oos_portfolio;
```
Should return one row.

⚠️ **Privilege required:** Metastore admin. If you don't see "Create credential" enabled, ask your Databricks account admin to grant you the role at Account Console → Metastores.

---

## Step 8 — Create the External Location

Run `notebooks/setup/02_external_location.sql` against your cluster. This creates an external location named `ext_lakehouse` pointing at `abfss://oos-portfolio@oosstorage.dfs.core.windows.net/`.

Or do it via UI:
- **Catalog** → **External Data** → **External Locations** → **Create location**
- Name: `ext_lakehouse`
- URL: `abfss://oos-portfolio@oosstorage.dfs.core.windows.net/`
- Storage credential: `cred_oos_portfolio`
- **Create** → **Test connection**

Test must pass before continuing. If it fails with permissions: RBAC from Step 4 hasn't propagated — wait 2 more minutes and retry.

---

## Step 9 — Create catalog, schemas, and volume

Open `notebooks/setup/00_run_all_setup.py` (the orchestrator) on your cluster and **Run all**. It executes:

| File | Creates |
|---|---|
| `01_storage_credential.sql` | (verify-only) |
| `02_external_location.sql` | `ext_lakehouse` |
| `03_catalog_schemas.sql` | catalog `oos_portfolio` + schemas `raw / bronze / silver / gold` |
| `04_volume.sql` | volume `oos_portfolio.raw.landing_zone` |
| `05_grants.sql` | (optional) permissions |

✅ Verify in any SQL cell:
```sql
SHOW CATALOGS;                              -- includes oos_portfolio
SHOW SCHEMAS IN oos_portfolio;              -- raw, bronze, silver, gold
SHOW VOLUMES IN oos_portfolio.raw;          -- landing_zone
```

---

## Step 10 — Create the Azure SQL Database (serving layer)

This is where the gold KPIs land via `notebooks/gold/08_push_to_azure_sql.py`.

Portal → top search → **"SQL databases"** → **+ Create**.

**Basics tab:**

| Field | Value |
|---|---|
| Resource group | `rg-oos-portfolio` |
| Database name | `oos_portfolio` |
| Server | **Create new** → name `oos-sql-server` |
| Server → Authentication | **Use SQL authentication** |
| Server → Admin login | `oosadmin` |
| Server → Password | strong (8–128 chars, ≥ 3 of: upper / lower / digit / symbol) |
| Server → Region | same as RG |
| Want to use SQL elastic pool | **No** |
| Workload environment | **Development** |
| Compute + storage | **Configure database** → **Basic** (5 DTUs, 2 GB) → **Apply** *(~$5/month, cheapest)* |
| Backup storage redundancy | **Locally-redundant backup storage** |

**Networking tab:**

| Field | Value |
|---|---|
| Connectivity method | **Public endpoint** |
| ✅ Allow Azure services and resources to access this server | **Yes** *(lets Databricks reach it)* |
| ✅ Add current client IPv4 address | **Yes** *(lets your laptop connect)* |

**Security tab:** leave defaults (Defender for SQL is optional and adds cost).

**Review + create** → **Create**. Provisioning takes 2–5 minutes.

### Step 10a — Create the table

After deployment → **Go to resource** (the database, not the server) → **Query editor (preview)** (left nav) → sign in with `oosadmin`.

Run:

```sql
USE oos_portfolio;

CREATE TABLE dbo.oos_agent_kpi (
    stock_code         VARCHAR(20)  NOT NULL,
    country            VARCHAR(50),
    tier               VARCHAR(15),
    current_balance    DECIMAL(12,2),
    corrected_forecast DECIMAL(12,2),
    oos_threshold      DECIMAL(12,2),
    is_oos             BIT,
    reorder_qty        DECIMAL(12,2),
    balance_color      VARCHAR(10),
    wape               DECIMAL(5,2),
    observation_date   DATE         NOT NULL,
    CONSTRAINT pk_oos_agent_kpi PRIMARY KEY (stock_code, observation_date)
);
CREATE INDEX idx_oos_country ON dbo.oos_agent_kpi(country);
CREATE INDEX idx_oos_tier    ON dbo.oos_agent_kpi(tier);
```

### Step 10b — Capture the host name

The server's **Overview** page shows:
```
oos-sql-server.database.windows.net    ← AZSQL_HOST
```

Paste it into `notebooks/config/pipeline_config.py` (`AZSQL_HOST`), or store user/password in a Databricks secret scope (paste the same values via `databricks secrets put-secret oos azsql_user` / `azsql_password`).

---

## Step 11 — Upload historical data via azcopy

Auto Loader watches the landing volume but the volume starts empty.
Use [`azcopy`](https://learn.microsoft.com/azure/storage/common/storage-use-azcopy-v10)
to push the daily-split CSVs from your laptop into the
`oos-portfolio` container's `landing/uci_retail/` folder.  This is a
one-time operation per data refresh.

Two pieces:
1. Generate a **container-scoped SAS token** so azcopy can write without
   needing the account key.
2. Run azcopy with the token.

### Step 11a — Generate the SAS token

A SAS (Shared Access Signature) is a time-limited, scoped URL signature.
Container-scoped (`sr=c`) lets you upload many files with one token.
Blob-scoped (`sr=b`) only works for one file — don't use that.

#### Option A — Azure Portal

Portal → storage account `oosstorage` → **Containers** → click `oos-portfolio` →
**Shared access tokens** (left nav of the container blade):

| Field | Value |
|---|---|
| Signing method | **Account key** |
| Signing key | **Key 1** |
| Stored access policy | None |
| **Permissions** | tick **Read, Add, Create, Write, Delete, List** *(`racwdl`)* |
| Start | now |
| Expiry | a few hours / days from now (longer = more risk if leaked) |
| Allowed protocols | **HTTPS only** |

Click **Generate SAS token and URL** → copy the **Blob SAS token** (the
query string starting with `?sv=…`).  Don't copy the URL above it — just
the token.

#### Option B — Azure CLI

```bash
az storage container generate-sas \
  --account-name oosstorage \
  --name oos-portfolio \
  --permissions racwdl \
  --expiry 2026-05-08T23:59:00Z \
  --https-only \
  --auth-mode login --as-user \
  --output tsv
```

The CLI prints just the token (no leading `?`).  Prepend `?` when storing.

⚠️ **Treat the SAS token like a password** — anyone with it can write to
your container until it expires.  Don't commit it to git, don't paste it
into chat / Slack.

### Step 11b — Run azcopy

Install once on macOS:
```bash
brew install azcopy
azcopy --version
```

Set the SAS as a shell variable so `&` characters don't trip the shell.
Single quotes preserve the literal string:

```bash
# Paste the SAS you generated in Step 11a between the single quotes.
# Format (do NOT use these placeholder values verbatim — generate your own):
SAS='?sp=racwdl&st=<START-UTC>&se=<EXPIRY-UTC>&spr=https&sv=<API-VERSION>&sr=c&sig=<SIGNATURE>'
```

#### One-file smoke test

Quick sanity check before the bulk upload — verifies SAS, network, and
target path are all correct:

```bash
azcopy copy "daily_files_bucketA/online_retail_2025-04-23.csv" \
  "https://oosstorage.blob.core.windows.net/oos-portfolio/landing/uci_retail/online_retail_2025-04-23.csv${SAS}"
```

Look for `Final Job Status: Completed` and `Total Number of Transfers: 1`.

#### Bulk upload (all CSVs from a folder)

The wildcard goes on the **source side**; the target URL ends with a `/`
so azcopy preserves the source filenames:

```bash
cd daily_files_bucketA
azcopy copy "*.csv" \
  "https://oosstorage.blob.core.windows.net/oos-portfolio/landing/uci_retail/${SAS}"
```

For ~300 files (~50 MB total) this completes in 10–20 seconds — azcopy
parallelises ~10 transfers at a time.  Expected output:

```
Number of File Transfers: 303
Number of File Transfers Completed: 303
Number of File Transfers Failed: 0
Final Job Status: Completed
```

### Step 11c — Verify the upload

Three places you can confirm the same files:

```bash
# Via azcopy
azcopy list \
  "https://oosstorage.blob.core.windows.net/oos-portfolio/landing/uci_retail/${SAS}" \
  | wc -l
```

```sql
-- In a Databricks SQL cell (the volume is the UC view of the same path)
LIST '/Volumes/oos_portfolio/raw/landing_zone/'
```

```
-- In Azure Portal: Storage → oos-portfolio → browse to landing/uci_retail/
```

All three should report the same file count.

> 📝 **Endpoint note** — azcopy uses `oosstorage.blob.core.windows.net`
> while Databricks's UC external location uses `oosstorage.dfs.core.windows.net`.
> Both endpoints reach the same backing storage on a hierarchical-namespace
> account, so files written via blob endpoint are immediately visible
> through the dfs endpoint and vice versa.

### Common azcopy pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `AuthenticationFailed: Server failed to authenticate the request` | SAS expired | Regenerate (Step 11a) and re-export `SAS` |
| `403 AuthorizationPermissionMismatch` | SAS missing `w` (write) or `c` (create) | Regenerate with `--permissions racwdl` |
| `AuthorizationResourceTypeMismatch` | Used a blob-scoped SAS (`sr=b`) for bulk upload | Generate container-scoped (`sr=c`) instead |
| Bulk upload created `…/landing/uci_retail/daily_files_bucketA/…` | Source path was the folder, not `*.csv` | Use `daily_files_bucketA/*.csv` (wildcard expands shell-side) |
| `Failed: connection refused` | Storage firewall blocks public access | Step 3 left it default-open; if you tightened it, add your client IP |
| Files uploaded but Auto Loader doesn't ingest them | Same filename re-uploaded; Auto Loader's checkpoint remembers it by path+size+mtime | Either rename files or wipe `_checkpoints/bronze_sales/` (see `notebooks/maintenance/reset_bronze.py`) |
| `&` characters in SAS get interpreted by the shell | SAS not quoted | Wrap in single quotes when assigning the variable |

---

## End-state verification

```bash
# All resources land in the same RG
az resource list --resource-group rg-oos-portfolio --output table
```

Expected rows:
- `oosstorage` (Microsoft.Storage/storageAccounts)
- `ac-oos-portfolio` (Microsoft.Databricks/accessConnectors)
- `dbw-oos-portfolio` (Microsoft.Databricks/workspaces)
- `oos-sql-server` (Microsoft.Sql/servers)
- `oos-sql-server/oos_portfolio` (Microsoft.Sql/servers/databases)

In Databricks SQL editor:
```sql
SHOW STORAGE CREDENTIALS;   -- includes cred_oos_portfolio
SHOW EXTERNAL LOCATIONS;    -- includes ext_lakehouse
SHOW CATALOGS;              -- includes oos_portfolio
SHOW VOLUMES IN oos_portfolio.raw;  -- includes landing_zone
```

In Azure SQL Query editor:
```sql
SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID('dbo');  -- includes oos_agent_kpi
```

---

## Cost summary (cheapest tiers, all running)

| Resource | Idle / running |
|---|---|
| Storage account (LRS, low traffic) | ~$0.05/GB/month |
| Access connector | Free |
| Databricks workspace | Free idle; cluster ~$0.40–0.80/hr while running + DBUs |
| Azure SQL Basic (5 DTU, 2 GB) | ~$5/month |
| **Total when actively iterating** | **~$5–10/month** |

To minimise:
- Stop the cluster when not running notebooks (auto-stop = 30 min)
- Pause the SQL DB between sessions (Portal → DB → ⋯ → Pause)

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `VALIDATE EXTERNAL LOCATION` fails with permissions error | RBAC from Step 4 not yet propagated | Wait 2–5 min, retry |
| Storage credential creation greyed out | You aren't a metastore admin | Ask account admin to grant the role |
| `Standard` workspace can't see UC settings | Wrong tier | Recreate workspace as **Premium**; standard tier doesn't support UC |
| Container creation rejected — "name contains invalid character" | Underscore in container name | Use `oos-portfolio` (hyphen) — that's the Azure rule |
| `CREATE CATALOG` fails with "Metastore storage root URL does not exist" | Newer Databricks account with no default storage root | Already handled in `notebooks/setup/03_catalog_schemas.sql` (catalog has explicit `MANAGED LOCATION`) — re-run setup |
| Azure SQL push fails with `Login failed for user` | Wrong password, or used `oosadmin@server` (legacy syntax) | Just `oosadmin` — Flexible Server doesn't use the @suffix |
| Azure SQL push hangs | Firewall blocks Databricks | Portal → SQL server → Networking → tick "Allow Azure services and resources to access this server" |

---

## Optional: Azure Data Factory (Day 6 orchestration)

Not required for the pipeline to work — the master notebook can be triggered manually or via Databricks Workflows. ADF is the production-grade orchestrator if your team uses it.

Portal → **"Data factories"** → **+ Create**:
- Resource group: `rg-oos-portfolio`
- Name: `adf-oos-portfolio`
- Region: same as RG
- Version: V2
- Configure git: optional

After deployment, in ADF Studio → **Author** → **+ Pipeline** → add a **Notebook** activity → linked service to your Databricks workspace → notebook path `/Workspace/Repos/<you>/.../notebooks/00_run_full_pipeline`. Trigger daily at 06:00 UTC.

## Optional: Log Analytics (Day 6 monitoring)

Portal → **"Log Analytics workspaces"** → **+ Create** → name `law-oos-portfolio`, RG `rg-oos-portfolio` → Create.

Then in ADF and Databricks → **Diagnostic settings** → "Send to Log Analytics workspace" → pick `law-oos-portfolio` → tick all log categories → Save.

KQL queries to keep handy:

```kql
// Last 24h ADF pipeline runs by status
ADFPipelineRun
| where TimeGenerated > ago(24h)
| summarize Runs = count() by Status, PipelineName

// Average notebook runtime per step
DatabricksNotebook
| where TimeGenerated > ago(7d)
| summarize avg(Duration) by NotebookPath
```

---

## IaC alternative (skipped for portfolio)

The Portal walkthrough above takes ~30–45 min the first time. For repeat
deployments, write the same as Bicep (`infrastructure/main.bicep`) or
Terraform — the resources, RBAC roles, and Databricks asset bundle config
are all available as ARM types. Beyond scope for this portfolio piece.
