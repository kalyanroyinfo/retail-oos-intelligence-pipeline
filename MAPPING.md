# Schema Mapping — UCI Online Retail → OOS Domain

The UCI Online Retail dataset is generic e-commerce transactions. We treat each
`StockCode` as a "selling agent" so the same forecasting + OOS logic applies as
in a real retail-stockout use case.

## Source columns

| UCI column    | Type      | Notes                              |
|---------------|-----------|------------------------------------|
| `InvoiceNo`   | string    | Transaction id (prefix `C` = cancellation) |
| `StockCode`   | string    | Product code                       |
| `Description` | string    | Product description (free text)    |
| `Quantity`    | int       | Units per line — can be negative (returns) |
| `InvoiceDate` | timestamp | Transaction timestamp              |
| `UnitPrice`   | double    | Price per unit (GBP)               |
| `CustomerID`  | string    | Customer (often null)              |
| `Country`     | string    | Shipping country                   |

## Domain mapping

| OOS concept   | Source                                       |
|---------------|----------------------------------------------|
| `agent_id`    | `StockCode`                                  |
| `total_sales` | `Quantity * UnitPrice`                       |
| `region`      | `Country`                                    |
| `tbl_dt`      | `to_date(InvoiceDate)`                       |
| `daily_sales` | sum of `total_sales` per agent per `tbl_dt`  |

## Calibration anchors (UCI percentiles, GBP)

- median daily sales: **£14.22**
- p25 / p75 / p95: **£7.50 / £26.86 / £79**
- ~3,941 unique products
- ~305 days of data

## OOS rule

```
is_oos = current_balance < max(OOS_THRESHOLD_FLOOR, forecast_daily_sales * OOS_THRESHOLD_DAYS)
       = current_balance < max(£5, forecast × 1.0)
```

`current_balance` is **simulated** for this dataset (see
`notebooks/silver/06_compute_balance_snapshot.py`) — UCI has no inventory column.

## Tier classification (daily revenue)

| Tier        | Avg daily sales (GBP) | Expected share |
|-------------|-----------------------|----------------|
| T1 — Gold   | ≥ £30                 | ~22%           |
| T2 — Silver | £8 – £30              | ~38%           |
| T3 — Bronze | < £8                  | ~40%           |

Cuts and clip ranges live in `notebooks/config/pipeline_config.py`.
