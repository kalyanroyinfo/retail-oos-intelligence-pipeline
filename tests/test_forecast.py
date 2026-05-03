"""Sanity checks for the forecast logic.

Runs locally via `pytest tests/` — no Databricks runtime needed.
The Spark notebooks themselves can't be unit-tested without a SparkSession,
so we replicate the small numerical bits here as plain Python/pandas.
"""

from statistics import median

import pandas as pd


def dow_median(df: pd.DataFrame) -> pd.DataFrame:
    """Median daily_sales per (StockCode, day-of-week) — mirrors silver/04 logic."""
    out = (
        df.assign(dow=pd.to_datetime(df["tbl_dt"]).dt.dayofweek)
          .groupby(["StockCode", "dow"], as_index=False)["daily_sales"]
          .median()
          .rename(columns={"daily_sales": "dow_median"})
    )
    return out


def test_dow_median_simple():
    # StockCode A: Mondays = [10, 20], Tuesdays = [5]
    # StockCode B: Mondays = [100]
    df = pd.DataFrame([
        {"StockCode": "A", "tbl_dt": "2024-01-01", "daily_sales": 10},   # Mon
        {"StockCode": "A", "tbl_dt": "2024-01-08", "daily_sales": 20},   # Mon
        {"StockCode": "A", "tbl_dt": "2024-01-02", "daily_sales": 5},    # Tue
        {"StockCode": "B", "tbl_dt": "2024-01-01", "daily_sales": 100},  # Mon
    ])
    out = dow_median(df).set_index(["StockCode", "dow"])["dow_median"].to_dict()

    assert out[("A", 0)] == median([10, 20])
    assert out[("A", 1)] == 5
    assert out[("B", 0)] == 100


def test_oos_threshold_floor():
    """oos_threshold = max(floor, forecast * days). Floor protects very-low-volume products."""
    floor = 5
    days  = 1.0

    cases = [
        # (forecast, expected_threshold)
        (0.0, 5.0),    # floor wins
        (3.0, 5.0),    # floor still wins
        (8.0, 8.0),    # forecast wins
        (10.0, 10.0),
    ]
    for forecast, expected in cases:
        assert max(floor, forecast * days) == expected, f"forecast={forecast}"


def test_bias_correction_clip():
    """bias_correction is clipped to BIAS_CORRECTION_CLIP = (0.5, 3.0)."""
    lo, hi = 0.5, 3.0
    cases = [(0.1, 0.5), (0.5, 0.5), (1.0, 1.0), (3.0, 3.0), (10.0, 3.0)]
    for raw, expected in cases:
        assert max(lo, min(hi, raw)) == expected, f"raw={raw}"
