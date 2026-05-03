# Infrastructure

Place Azure CLI scripts, Bicep templates, or Terraform here if/when you
provision via IaC. The 7-day plan provisions resources via `az` CLI commands
embedded in `README.md` Days 1–2; nothing lives here yet.

Suggested files:

- `provision.sh` — wraps the `az group create` / `az storage account create`
  / `az databricks access-connector create` steps from Day 2.
- `bicep/main.bicep` — declarative version of the same.
