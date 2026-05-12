"""
Sales ETL Pipeline — SalesETL class
Extracts, validates, transforms, and loads the Superstore dataset.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


class SalesETL:
    def __init__(self, raw_path: str, output_dir: str) -> None:
        self.raw_path = Path(raw_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # EXTRACT
    def extract(self) -> pd.DataFrame:
        df = pd.read_csv(
            self.raw_path,
            encoding="latin-1",
            parse_dates=["Order Date", "Ship Date"],
            dayfirst=False,
        )

        # Normalise dates that may have loaded as strings
        for col in ("Order Date", "Ship Date"):
            if not pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = pd.to_datetime(df[col], format="%m/%d/%Y")

        # Strip whitespace from all string columns
        str_cols = df.select_dtypes(include="object").columns
        df[str_cols] = df[str_cols].apply(lambda s: s.str.strip())

        print(f"[EXTRACT] {len(df):,} rows loaded from {self.raw_path.name}")
        return df

    # VALIDATE
    def validate(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        df = df.copy()
        issues: dict = {}

        # Null counts
        null_counts = df.isnull().sum()
        null_issues = null_counts[null_counts > 0].to_dict()
        issues["null_counts"] = null_issues
        if null_issues:
            print(f"[VALIDATE] Null values detected: {null_issues}")
        else:
            print("[VALIDATE] No null values found")

        # Duplicate Order ID + Product ID
        dup_mask = df.duplicated(subset=["Order ID", "Product ID"], keep=False)
        dup_count = dup_mask.sum()
        issues["duplicate_order_product"] = int(dup_count)
        if dup_count:
            print(f"[VALIDATE] {dup_count} duplicate Order ID + Product ID combinations")

        # Initialise anomaly flag
        df["is_anomaly"] = False

        # Sales <= 0
        sales_zero = df["Sales"] <= 0
        df.loc[sales_zero, "is_anomaly"] = True
        issues["sales_lte_zero"] = int(sales_zero.sum())
        if sales_zero.any():
            print(f"[VALIDATE] {sales_zero.sum()} rows with Sales <= 0 — flagged as anomaly")

        # Discount outside 0–0.8
        bad_discount = (df["Discount"] < 0) | (df["Discount"] > 0.8)
        df.loc[bad_discount, "is_anomaly"] = True
        issues["discount_out_of_range"] = int(bad_discount.sum())
        if bad_discount.any():
            print(f"[VALIDATE] {bad_discount.sum()} rows with Discount outside 0–0.8 — flagged")

        # Quantity <= 0
        qty_zero = df["Quantity"] <= 0
        df.loc[qty_zero, "is_anomaly"] = True
        issues["quantity_lte_zero"] = int(qty_zero.sum())
        if qty_zero.any():
            print(f"[VALIDATE] {qty_zero.sum()} rows with Quantity <= 0 — flagged")

        # Profit > Sales (impossible margin)
        impossible_margin = df["Profit"] > df["Sales"]
        df.loc[impossible_margin, "is_anomaly"] = True
        issues["profit_exceeds_sales"] = int(impossible_margin.sum())
        if impossible_margin.any():
            print(
                f"[VALIDATE] {impossible_margin.sum()} rows where Profit > Sales — flagged as anomaly"
            )

        total_flagged = int(df["is_anomaly"].sum())
        issues["total_anomalies"] = total_flagged
        issues["total_rows"] = len(df)
        issues["clean_rows"] = len(df) - total_flagged

        print(
            f"[VALIDATE] {len(df):,} total rows | {len(df) - total_flagged:,} clean"
            f" | {total_flagged:,} flagged"
        )
        return df, issues

    # TRANSFORM
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # FINANCIAL
        df["revenue"] = df["Sales"]
        df["cost"] = df["Sales"] - df["Profit"]
        df["margin_pct"] = np.where(
            df["Sales"] == 0, 0.0, (df["Profit"] / df["Sales"]) * 100
        )
        df["unit_price"] = np.where(
            df["Quantity"] == 0, 0.0, df["Sales"] / df["Quantity"]
        )
        df["discount_pct"] = df["Discount"] * 100

        # TIME
        df["order_year"] = df["Order Date"].dt.year.astype(int)
        df["order_month"] = df["Order Date"].dt.strftime("%Y-%m")
        df["order_quarter"] = (
            "Q" + df["Order Date"].dt.quarter.astype(str)
            + " " + df["Order Date"].dt.year.astype(str)
        )
        df["ship_days"] = (df["Ship Date"] - df["Order Date"]).dt.days

        # PRODUCT
        df["category_clean"] = df["Category"].str.strip().str.title()
        df["sub_category_clean"] = df["Sub-Category"].str.strip()

        # GEOGRAPHY
        df["region_clean"] = df["Region"].str.strip().str.title()

        # SEGMENTATION
        sales_75th = df["Sales"].quantile(0.75)
        df["is_high_value_order"] = df["Sales"] > sales_75th

        df["profit_tier"] = pd.cut(
            df["margin_pct"],
            bins=[-np.inf, 0, 10, 20, np.inf],
            labels=["Loss", "Low", "Medium", "High"],
            right=False,
        ).astype(str)
        # Rows where Profit < 0 → Loss regardless of margin_pct
        df.loc[df["Profit"] < 0, "profit_tier"] = "Loss"

        print(
            f"[TRANSFORM] Derived columns added: revenue, cost, margin_pct, unit_price, "
            f"discount_pct, order_year, order_month, order_quarter, ship_days, "
            f"category_clean, sub_category_clean, region_clean, "
            f"is_high_value_order, profit_tier"
        )
        return df

    # LOAD
    def load(self, df: pd.DataFrame) -> dict:
        paths: dict = {}

        # fact_sales.csv
        fact_path = self.output_dir / "fact_sales.csv"
        df.to_csv(fact_path, index=False)
        paths["fact_sales"] = str(fact_path)
        print(f"[LOAD] fact_sales.csv — {len(df):,} rows → {fact_path}")

        # monthly_trend.csv
        monthly = (
            df.groupby("order_month")
            .agg(
                total_revenue=("revenue", "sum"),
                total_profit=("Profit", "sum"),
                total_orders=("Order ID", "nunique"),
                total_units=("Quantity", "sum"),
                avg_margin_pct=("margin_pct", "mean"),
            )
            .reset_index()
            .sort_values("order_month")
        )
        monthly["mom_revenue_growth_pct"] = monthly["total_revenue"].pct_change() * 100
        monthly_path = self.output_dir / "monthly_trend.csv"
        monthly.to_csv(monthly_path, index=False)
        paths["monthly_trend"] = str(monthly_path)
        print(f"[LOAD] monthly_trend.csv — {len(monthly)} rows → {monthly_path}")

        # regional_performance.csv
        regional = (
            df.groupby(["Region", "order_year"])
            .agg(
                total_revenue=("revenue", "sum"),
                total_profit=("Profit", "sum"),
                avg_margin_pct=("margin_pct", "mean"),
                total_orders=("Order ID", "nunique"),
                total_customers=("Customer ID", "nunique"),
            )
            .reset_index()
            .rename(columns={"Region": "region", "order_year": "year"})
            .sort_values(["region", "year"])
        )
        regional["yoy_growth_pct"] = regional.groupby("region")["total_revenue"].pct_change() * 100
        regional_path = self.output_dir / "regional_performance.csv"
        regional.to_csv(regional_path, index=False)
        paths["regional_performance"] = str(regional_path)
        print(f"[LOAD] regional_performance.csv — {len(regional)} rows → {regional_path}")

        # product_performance.csv
        product = (
            df.groupby(["Category", "Sub-Category", "Product Name"])
            .agg(
                total_revenue=("revenue", "sum"),
                total_profit=("Profit", "sum"),
                avg_margin_pct=("margin_pct", "mean"),
                total_units=("Quantity", "sum"),
                order_count=("Order ID", "nunique"),
            )
            .reset_index()
            .rename(
                columns={
                    "Category": "category",
                    "Sub-Category": "sub_category",
                    "Product Name": "product_name",
                }
            )
        )
        product["revenue_rank"] = (
            product.groupby("category")["total_revenue"]
            .rank(ascending=False, method="min")
            .astype(int)
        )
        product_path = self.output_dir / "product_performance.csv"
        product.to_csv(product_path, index=False)
        paths["product_performance"] = str(product_path)
        print(f"[LOAD] product_performance.csv — {len(product)} rows → {product_path}")

        # segment_performance.csv
        seg_list = []
        for (seg, yr), grp in df.groupby(["Segment", "order_year"]):
            total_customers = grp["Customer ID"].nunique()
            # Repeat customers: customers with > 1 order in that year
            orders_per_cust = grp.groupby("Customer ID")["Order ID"].nunique()
            repeat = (orders_per_cust > 1).sum()
            repeat_rate = repeat / total_customers if total_customers > 0 else 0.0
            seg_list.append(
                {
                    "segment": seg,
                    "year": yr,
                    "total_revenue": grp["revenue"].sum(),
                    "total_profit": grp["Profit"].sum(),
                    "avg_margin_pct": grp["margin_pct"].mean(),
                    "avg_order_value": grp.groupby("Order ID")["revenue"].sum().mean(),
                    "total_customers": total_customers,
                    "repeat_customer_rate": round(repeat_rate, 4),
                }
            )
        segment = pd.DataFrame(seg_list)
        segment_path = self.output_dir / "segment_performance.csv"
        segment.to_csv(segment_path, index=False)
        paths["segment_performance"] = str(segment_path)
        print(f"[LOAD] segment_performance.csv — {len(segment)} rows → {segment_path}")

        # exec_summary.json
        top_region = (
            df.groupby("Region")["revenue"].sum().idxmax()
        )
        top_category = (
            df.groupby("Category")["revenue"].sum().idxmax()
        )
        top_segment = (
            df.groupby("Segment")["revenue"].sum().idxmax()
        )
        top_state = (
            df.groupby("State")["revenue"].sum().idxmax()
        )
        top_product = (
            df.groupby("Product Name")["revenue"].sum().idxmax()
        )
        worst_margin_category = (
            df.groupby("Category")["margin_pct"].mean().idxmin()
        )

        rev_by_month = (
            df.groupby("order_month")
            .agg(revenue=("revenue", "sum"), profit=("Profit", "sum"))
            .reset_index()
            .rename(columns={"order_month": "month"})
            .to_dict("records")
        )
        rev_by_region = (
            df.groupby("Region")
            .agg(revenue=("revenue", "sum"), margin_pct=("margin_pct", "mean"))
            .reset_index()
            .rename(columns={"Region": "region"})
            .to_dict("records")
        )
        rev_by_category = (
            df.groupby("Category")
            .agg(revenue=("revenue", "sum"), margin_pct=("margin_pct", "mean"))
            .reset_index()
            .rename(columns={"Category": "category"})
            .to_dict("records")
        )
        rev_by_segment = (
            df.groupby("Segment")
            .agg(revenue=("revenue", "sum"), margin_pct=("margin_pct", "mean"))
            .reset_index()
            .rename(columns={"Segment": "segment"})
            .to_dict("records")
        )

        summary = {
            "total_revenue": round(float(df["revenue"].sum()), 2),
            "total_profit": round(float(df["Profit"].sum()), 2),
            "overall_margin_pct": round(
                float(df["Profit"].sum() / df["revenue"].sum() * 100), 2
            ),
            "total_orders": int(df["Order ID"].nunique()),
            "total_customers": int(df["Customer ID"].nunique()),
            "total_products": int(df["Product ID"].nunique()),
            "date_range": {
                "start": df["Order Date"].min().strftime("%Y-%m-%d"),
                "end": df["Order Date"].max().strftime("%Y-%m-%d"),
            },
            "top_region": str(top_region),
            "top_category": str(top_category),
            "top_segment": str(top_segment),
            "top_state": str(top_state),
            "top_product": str(top_product),
            "worst_margin_category": str(worst_margin_category),
            "avg_ship_days": round(float(df["ship_days"].mean()), 2),
            "revenue_by_month": rev_by_month,
            "revenue_by_region": rev_by_region,
            "revenue_by_category": rev_by_category,
            "revenue_by_segment": rev_by_segment,
        }

        summary_path = self.output_dir / "exec_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        paths["exec_summary"] = str(summary_path)
        print(f"[LOAD] exec_summary.json → {summary_path}")

        return paths

    # RUN
    def run(self) -> pd.DataFrame:
        raw = self.extract()
        validated, issues = self.validate(raw)
        transformed = self.transform(validated)
        self.load(transformed)
        return transformed


# CLI entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Superstore Sales ETL pipeline")
    parser.add_argument(
        "--input",
        default="data/raw/superstore.csv",
        help="Path to raw superstore.csv",
    )
    parser.add_argument(
        "--output",
        default="output/",
        help="Output directory for CSV/JSON files",
    )
    args = parser.parse_args()
    etl = SalesETL(raw_path=args.input, output_dir=args.output)
    etl.run()
