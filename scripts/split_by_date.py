"""Split the UCI Online Retail CSV into one file per InvoiceDate.

Run once locally before Day 2. Output goes to ./daily_files/online_retail_<YYYY-MM-DD>.csv.

Usage:
    python scripts/split_by_date.py --src online_retail.csv --out daily_files
"""

import argparse
import os
import pandas as pd


def split_by_date(src: str, out_dir: str) -> int:
    df = pd.read_csv(src, parse_dates=["InvoiceDate"])
    df["sale_date"] = df["InvoiceDate"].dt.date
    os.makedirs(out_dir, exist_ok=True)

    for d, group in df.groupby("sale_date"):
        path = os.path.join(out_dir, f"online_retail_{d}.csv")
        group.drop(columns=["sale_date"]).to_csv(path, index=False)

    return df["sale_date"].nunique()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--src", default="online_retail.csv")
    p.add_argument("--out", default="daily_files")
    args = p.parse_args()

    n = split_by_date(args.src, args.out)
    print(f"Created {n} daily files in {args.out}/")
