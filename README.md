# Superstore Sales Performance Dashboard

A multi-source sales ETL pipeline with dbt-style SQL models and an interactive Streamlit executive dashboard — built on the real Superstore dataset.

---

## Dataset

**Superstore Sales** — 9,994 orders, 793 customers, 4 years (2014–2017)  
21 columns covering orders, products, customers, geography, and financials.

Download from: [Kaggle — Superstore Dataset](https://www.kaggle.com/datasets/vivek468/superstore-dataset-final)  
Place at: `data/raw/superstore.csv`

---

## Architecture

```
superstore.csv
│
▼
[EXTRACT]  parse dates, detect encoding (latin-1)
│
▼
[VALIDATE] flag anomalies, check ranges
│
▼
[TRANSFORM] derive cost, margin, time columns
│
├──→ fact_sales.csv
├──→ monthly_trend.csv
├──→ regional_performance.csv
├──→ product_performance.csv
├──→ segment_performance.csv
└──→ exec_summary.json
│
▼
Streamlit Dashboard
(KPIs · Trends · Products · Regions · Customers)
```

**Parallel SQL path (DuckDB):**

```
superstore.csv
    → stg_orders          (normalise, cast types, dedup key)
    → int_sales_enriched  (full fact + derived columns)
    → mart_*              (regional, product, segment, state, KPI views)
```

---

## Project Structure

```
sales-dashboard/
├── app.py                          Streamlit executive dashboard
├── requirements.txt
├── .streamlit/
│   └── config.toml                 Theme configuration
├── src/
│   ├── __init__.py
│   ├── etl.py                      ETL pipeline (SalesETL class)
│   └── models.sql                  dbt-style DuckDB SQL models
├── tests/
│   ├── __init__.py
│   └── test_etl.py                 14 pytest unit tests
├── data/
│   └── raw/
│       └── superstore.csv          ← download and place here
├── output/
│   ├── fact_sales.csv
│   ├── regional_performance.csv
│   ├── product_performance.csv
│   ├── segment_performance.csv
│   ├── monthly_trend.csv
│   └── exec_summary.json
└── README.md
```

---

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download dataset and place at:
#    data/raw/superstore.csv

# 3. Run the ETL pipeline
python src/etl.py --input data/raw/superstore.csv --output output/

# 4. Launch the dashboard
streamlit run app.py
```

---

## Run SQL Models (DuckDB)

```bash
duckdb superstore.ddb
```

```sql
CREATE OR REPLACE TABLE raw_superstore AS
SELECT * FROM read_csv_auto(
    'data/raw/superstore.csv',
    header=true,
    dateformat='%m/%d/%Y'
);

.read src/models.sql

SELECT * FROM mart_regional_performance;
SELECT * FROM mart_product_performance WHERE category = 'Technology';
SELECT * FROM mart_exec_kpis;
SELECT * FROM mart_state_performance LIMIT 10;
```

---

## Run Tests

```bash
pytest tests/ -v
```

Expected output: **14 passed**.

| Test | Description |
|------|-------------|
| `test_extract_loads_correct_row_count` | Expects 9,994 rows |
| `test_extract_parses_dates_correctly` | Order Date is datetime dtype |
| `test_validate_detects_anomalies` | Injected Sales=0 row flagged |
| `test_validate_returns_issues_dict` | Dict has all required keys |
| `test_transform_computes_cost_correctly` | cost = Sales − Profit |
| `test_transform_computes_margin_pct` | margin = Profit/Sales × 100 |
| `test_transform_handles_zero_sales` | No division by zero |
| `test_transform_creates_order_month` | Format "YYYY-MM" |
| `test_transform_creates_profit_tier` | All values in {Loss, Low, Medium, High} |
| `test_transform_creates_ship_days` | All values ≥ 0 |
| `test_load_creates_all_output_files` | 6 files written |
| `test_exec_summary_json_structure` | All required keys present |
| `test_monthly_trend_mom_growth` | First month growth is NaN |
| `test_product_performance_revenue_rank` | Rank 1 = highest revenue in category |

---

## Dashboard Sections

| Section | Content |
|---------|---------|
| **KPI Header** | Revenue, Profit, Margin %, Orders, Avg Ship Days — all with YoY deltas |
| **Revenue Trend** | Monthly line chart + Region/Category/Segment breakdowns |
| **Product Deep Dive** | Sub-category treemap (coloured by margin) + top/bottom performers |
| **Regional Performance** | Grouped bar by year/region + US choropleth + YoY growth table |
| **Customer & Order Analysis** | Ship mode, top customers, Discount vs Margin scatter |
| **Data Quality Report** | Null counts, anomalies, flagged rows |

---

## Key Findings

- **Technology** is the highest-revenue category; **Office Supplies** has the better margin
- The **West** region leads revenue; the **South** has the lowest margin %
- **Furniture** sub-categories (Tables, Bookcases) are loss-making at high discount rates
- The "Discount vs Margin" scatter clearly shows margin collapses above **20% discount**
- **Standard Class** is the most-used ship mode; **Same Day** has the fastest fulfilment

---

## Extending This Project

- Connect to a live data source (Salesforce, Shopify API) instead of CSV
- Add a sales forecasting model (Prophet or ARIMA) for next-quarter projections
- Run SQL models on a cloud warehouse (Snowflake, BigQuery) — `models.sql` is compatible
- Add a dbt project layer (`dbt init`, `schema.yml`, tests) on top of `models.sql`
- Schedule ETL with Airflow for nightly refresh

---

## Tech Stack

| Tool | Role |
|------|------|
| Python / pandas | ETL pipeline |
| DuckDB | SQL model execution — serverless, no setup |
| Streamlit | Interactive dashboard |
| Plotly | Line, bar, treemap, choropleth, scatter charts |
| pytest | 14 unit tests |

---

## Author

[Your Name] · [LinkedIn] · [Portfolio]
