# Databricks notebook source
# notebooks/gold/08_push_to_postgres.py
# Push gold KPIs to Azure PostgreSQL via Spark JDBC.
#
# Credentials: prefer a Databricks secret scope. Set up once with:
#   databricks secrets create-scope --scope oos
#   databricks secrets put --scope oos --key pg_user
#   databricks secrets put --scope oos --key pg_password

# COMMAND ----------

# MAGIC %run ../config/pipeline_config

# COMMAND ----------

dbutils.widgets.text("run_date", "")
dbutils.widgets.text("env", "dev")
dbutils.widgets.text("secret_scope", "oos")
run_date     = dbutils.widgets.get("run_date")
secret_scope = dbutils.widgets.get("secret_scope")

# COMMAND ----------

# Resolve credentials: secret scope first, fall back to placeholders in config.
def _resolve(scope: str, key: str, fallback: str) -> str:
    try:
        return dbutils.secrets.get(scope=scope, key=key)
    except Exception:
        return fallback


pg_user     = _resolve(secret_scope, "pg_user",     PG_USER)
pg_password = _resolve(secret_scope, "pg_password", PG_PASSWORD)

jdbc_url = (
    f"jdbc:postgresql://{PG_HOST}:5432/{PG_DB}"
    f"?sslmode=require"
)

# COMMAND ----------

sdf_gold = spark.table(T_GOLD_KPI)

(sdf_gold.write
    .format("jdbc")
    .option("url", jdbc_url)
    .option("driver", "org.postgresql.Driver")
    .option("dbtable", PG_TABLE)
    .option("user", pg_user)
    .option("password", pg_password)
    .option("truncate", "true")
    .mode("overwrite")
    .save())

# COMMAND ----------

row_count = sdf_gold.count()
dbutils.notebook.exit(f"push_postgres rows={row_count} run_date={run_date}")
