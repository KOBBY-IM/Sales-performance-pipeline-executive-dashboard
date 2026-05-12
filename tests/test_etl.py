"""
pytest unit tests for SalesETL
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.etl import SalesETL

# Fixtures
RAW_PATH = Path("data/raw/superstore.csv")
OUTPUT_DIR = Path("output_test")


@pytest.fixture(scope="session")
def etl(tmp_path_factory):
    out = tmp_path_factory.mktemp("output")
    return SalesETL(raw_path=str(RAW_PATH), output_dir=str(out))


@pytest.fixture(scope="session")
def raw_df(etl):
    return etl.extract()


@pytest.fixture(scope="session")
def validated(etl, raw_df):
    return etl.validate(raw_df)


@pytest.fixture(scope="session")
def transformed(etl, validated):
    clean_df, _ = validated
    return etl.transform(clean_df)


@pytest.fixture(scope="session")
def loaded_paths(etl, transformed):
    return etl.load(transformed)


# EXTRACT tests
def test_extract_loads_correct_row_count(raw_df):
    """Expect 9,994 rows in the Superstore dataset."""
    assert len(raw_df) == 9994, f"Expected 9994 rows, got {len(raw_df)}"


def test_extract_parses_dates_correctly(raw_df):
    """Order Date column must be datetime dtype."""
    assert pd.api.types.is_datetime64_any_dtype(raw_df["Order Date"]), (
        "Order Date should be datetime64"
    )


# VALIDATE tests
def test_validate_detects_anomalies(etl):
    """Injecting a Sales=0 row must set is_anomaly=True for that row."""
    base_df = pd.DataFrame(
        {
            "Order ID": ["A-001"],
            "Product ID": ["P-001"],
            "Sales": [0.0],
            "Profit": [5.0],
            "Discount": [0.1],
            "Quantity": [1],
            "Order Date": [pd.Timestamp("2016-01-01")],
            "Ship Date": [pd.Timestamp("2016-01-03")],
            "Region": ["East"],
            "Category": ["Furniture"],
            "Sub-Category": ["Chairs"],
            "Product Name": ["Chair A"],
            "Customer ID": ["C-001"],
            "Segment": ["Consumer"],
            "State": ["New York"],
        }
    )
    clean, _ = etl.validate(base_df)
    assert clean.loc[clean["Order ID"] == "A-001", "is_anomaly"].iloc[0] is True or \
           bool(clean.loc[clean["Order ID"] == "A-001", "is_anomaly"].iloc[0]) is True


def test_validate_returns_issues_dict(validated):
    """validate() must return a dict containing expected keys."""
    _, issues = validated
    required_keys = {
        "null_counts",
        "duplicate_order_product",
        "sales_lte_zero",
        "discount_out_of_range",
        "quantity_lte_zero",
        "profit_exceeds_sales",
        "total_anomalies",
        "total_rows",
        "clean_rows",
    }
    missing = required_keys - set(issues.keys())
    assert not missing, f"Missing keys in issues dict: {missing}"


# TRANSFORM tests
def test_transform_computes_cost_correctly(transformed):
    """cost = Sales - Profit for every row."""
    diff = (transformed["Sales"] - transformed["Profit"] - transformed["cost"]).abs()
    assert diff.max() < 1e-6, "cost column does not equal Sales - Profit"


def test_transform_computes_margin_pct(transformed):
    """margin_pct = (Profit / Sales) * 100 where Sales != 0."""
    non_zero = transformed[transformed["Sales"] != 0].copy()
    expected = (non_zero["Profit"] / non_zero["Sales"]) * 100
    diff = (non_zero["margin_pct"] - expected).abs()
    assert diff.max() < 1e-6, "margin_pct computation is incorrect"


def test_transform_handles_zero_sales(transformed):
    """No NaN or inf values in margin_pct (zero-sales rows should be 0)."""
    assert not transformed["margin_pct"].isnull().any(), "margin_pct has NaN values"
    assert not np.isinf(transformed["margin_pct"]).any(), "margin_pct has inf values"


def test_transform_creates_order_month(transformed):
    """order_month must match 'YYYY-MM' format."""
    sample = transformed["order_month"].dropna().head(20)
    for val in sample:
        assert len(val) == 7 and val[4] == "-", f"Unexpected order_month format: {val}"


def test_transform_creates_profit_tier(transformed):
    """All profit_tier values must be in the expected set."""
    valid_tiers = {"Loss", "Low", "Medium", "High"}
    actual = set(transformed["profit_tier"].unique())
    unexpected = actual - valid_tiers
    assert not unexpected, f"Unexpected profit_tier values: {unexpected}"


def test_transform_creates_ship_days(transformed):
    """ship_days must be >= 0 for all rows."""
    assert (transformed["ship_days"] >= 0).all(), "Some ship_days values are negative"


# LOAD tests
def test_load_creates_all_output_files(loaded_paths):
    """load() must produce 6 output files."""
    expected_keys = {
        "fact_sales",
        "monthly_trend",
        "regional_performance",
        "product_performance",
        "segment_performance",
        "exec_summary",
    }
    missing = expected_keys - set(loaded_paths.keys())
    assert not missing, f"Missing output files: {missing}"
    for key, path in loaded_paths.items():
        assert Path(path).exists(), f"File does not exist: {path}"


def test_exec_summary_json_structure(loaded_paths):
    """exec_summary.json must contain all required top-level keys."""
    with open(loaded_paths["exec_summary"]) as f:
        summary = json.load(f)

    required_keys = {
        "total_revenue", "total_profit", "overall_margin_pct",
        "total_orders", "total_customers", "total_products",
        "date_range", "top_region", "top_category", "top_segment",
        "top_state", "top_product", "worst_margin_category",
        "avg_ship_days", "revenue_by_month", "revenue_by_region",
        "revenue_by_category", "revenue_by_segment",
    }
    missing = required_keys - set(summary.keys())
    assert not missing, f"exec_summary.json is missing keys: {missing}"


def test_monthly_trend_mom_growth(loaded_paths):
    """First row's mom_revenue_growth_pct should be NaN (no prior month)."""
    monthly = pd.read_csv(loaded_paths["monthly_trend"])
    first_val = monthly["mom_revenue_growth_pct"].iloc[0]
    assert pd.isna(first_val) or first_val is None, (
        f"First month MoM growth should be NaN, got {first_val}"
    )


def test_product_performance_revenue_rank(loaded_paths):
    """Rank 1 within each category should be the product with the highest revenue."""
    prod = pd.read_csv(loaded_paths["product_performance"])
    for cat, grp in prod.groupby("category"):
        rank1 = grp[grp["revenue_rank"] == 1]["total_revenue"].values
        max_rev = grp["total_revenue"].max()
        assert len(rank1) >= 1, f"No rank-1 product found for category: {cat}"
        assert rank1[0] == max_rev, (
            f"Rank-1 product in '{cat}' does not have the highest revenue"
        )
