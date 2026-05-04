# Databricks notebook source
# notebooks/gold/08_push_to_azure_sql.py
# Push gold KPIs to Azure SQL Database (Microsoft SQL Server) via Spark JDBC.
#
# Cluster prereq — the SQL Server JDBC driver is BUNDLED with Databricks
# Runtime 13.x+, so no Maven library install is required.  If you ever
# need a newer version, attach `com.microsoft.sqlserver:mssql-jdbc:12.6.1.jre11`
# via Compute > <cluster> > Libraries > Install new > Maven.
#
# Credentials: prefer a Databricks secret scope. Set up once with:
#   databricks secrets create-scope --scope oos
#   databricks secrets put --scope oos --key azsql_user
#   databricks secrets put --scope oos --key azsql_password

# COMMAND ----------

# MAGIC %run ../config/pipeline_config

# COMMAND ----------

from datetime import datetime
_today = str(datetime.utcnow().date())
dbutils.widgets.text("run_date",     _today)
dbutils.widgets.text("env",          "dev")
dbutils.widgets.text("secret_scope", "oos")
run_date     = dbutils.widgets.get("run_date") or _today
secret_scope = dbutils.widgets.get("secret_scope")

# COMMAND ----------

# Resolve credentials: secret scope first, fall back to placeholders in config.
def _resolve(scope: str, key: str, fallback: str) -> str:
    try:
        return dbutils.secrets.get(scope=scope, key=key)
    except Exception:
        return fallback


azsql_user     = _resolve(secret_scope, "azsql_user",     AZSQL_USER)
azsql_password = _resolve(secret_scope, "azsql_password", AZSQL_PASSWORD)

# Azure SQL Database requires encryption.  Server cert is signed by a
# Microsoft CA, so trustServerCertificate=false (the default) is correct.
jdbc_url = (
    f"jdbc:sqlserver://{AZSQL_HOST}:1433"
    f";database={AZSQL_DB}"
    f";encrypt=true"
    f";trustServerCertificate=false"
    f";loginTimeout=30"
)

# COMMAND ----------

sdf_gold = spark.table(T_GOLD_KPI)

(sdf_gold.write
    .format("jdbc")
    .option("url", jdbc_url)
    .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
    .option("dbtable", AZSQL_TABLE)
    .option("user", azsql_user)
    .option("password", azsql_password)
    .option("truncate", "true")
    .mode("overwrite")
    .save())

# COMMAND ----------

row_count = sdf_gold.count()
dbutils.notebook.exit(f"push_azure_sql rows={row_count} run_date={run_date}")
