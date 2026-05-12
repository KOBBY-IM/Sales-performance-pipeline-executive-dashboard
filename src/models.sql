-- Superstore Sales — dbt-style SQL Models (DuckDB-compatible)
-- Run instructions:
--   duckdb superstore.ddb
--   > .read src/models.sql
--   > SELECT * FROM mart_regional_performance;
--   > SELECT * FROM mart_product_performance WHERE category = 'Technology';

-- Load raw table first
CREATE OR REPLACE TABLE raw_superstore AS
SELECT *
FROM read_csv_auto(
    'data/raw/superstore.csv',
    header = true,
    dateformat = '%m/%d/%Y'
);

-- STAGING LAYER — normalise, type-cast, extract dimensions

-- stg_orders: normalise column names, cast types, add derived columns
CREATE OR REPLACE VIEW stg_orders AS
SELECT
    "Row ID"::INTEGER                              AS row_id,
    "Order ID"                                     AS order_id,
    CAST("Order Date" AS DATE)                     AS order_date,
    CAST("Ship Date"  AS DATE)                     AS ship_date,
    "Ship Mode"                                    AS ship_mode,
    "Customer ID"                                  AS customer_id,
    "Customer Name"                                AS customer_name,
    "Segment"                                      AS segment,
    "Country"                                      AS country,
    "City"                                         AS city,
    "State"                                        AS state,
    "Postal Code"::VARCHAR                         AS postal_code,
    "Region"                                       AS region,
    "Product ID"                                   AS product_id,
    "Category"                                     AS category,
    "Sub-Category"                                 AS sub_category,
    "Product Name"                                 AS product_name,
    CAST("Sales"    AS DECIMAL(10,2))              AS sales,
    CAST("Quantity" AS INTEGER)                    AS quantity,
    CAST("Discount" AS DECIMAL(10,4))              AS discount,
    CAST("Profit"   AS DECIMAL(10,2))              AS profit,
    -- Derived
    CAST("Ship Date" AS DATE) - CAST("Order Date" AS DATE) AS ship_days,
    -- Dedup key
    MD5(
        COALESCE("Order ID", '') ||
        COALESCE("Product ID", '') ||
        COALESCE(CAST("Order Date" AS VARCHAR), '')
    ) AS row_hash
FROM raw_superstore
WHERE "Sales"    IS NOT NULL
  AND "Quantity" IS NOT NULL;


-- stg_products: distinct product dimension
CREATE OR REPLACE VIEW stg_products AS
SELECT DISTINCT
    product_id,
    product_name,
    category,
    sub_category
FROM stg_orders;


-- stg_customers: distinct customer dimension
CREATE OR REPLACE VIEW stg_customers AS
SELECT DISTINCT
    customer_id,
    customer_name,
    segment
FROM stg_orders;


-- stg_geography: distinct geography dimension
CREATE OR REPLACE VIEW stg_geography AS
SELECT DISTINCT
    city,
    state,
    region,
    country,
    postal_code
FROM stg_orders;


-- INTERMEDIATE LAYER — enriched analytical fact table and summaries

-- int_sales_enriched: full analytical fact with all derived columns
CREATE OR REPLACE VIEW int_sales_enriched AS
SELECT
    *,
    -- Financial
    sales                                                           AS revenue,
    sales - profit                                                  AS cost,
    ROUND(profit / NULLIF(sales, 0) * 100, 2)                      AS margin_pct,
    ROUND(sales  / NULLIF(quantity, 0), 2)                         AS unit_price,
    -- Time
    DATE_TRUNC('month', order_date)                                 AS order_month,
    'Q' || QUARTER(order_date) || ' ' || YEAR(order_date)          AS order_quarter,
    YEAR(order_date)                                                AS order_year,
    -- Profit tier
    CASE
        WHEN profit < 0                                THEN 'Loss'
        WHEN ROUND(profit / NULLIF(sales,0)*100,2) < 10
                                                       THEN 'Low'
        WHEN ROUND(profit / NULLIF(sales,0)*100,2) BETWEEN 10 AND 20
                                                       THEN 'Medium'
        ELSE                                                'High'
    END                                                             AS profit_tier
FROM stg_orders;


-- int_monthly_summary: monthly KPI aggregation with MoM growth
CREATE OR REPLACE VIEW int_monthly_summary AS
WITH base AS (
    SELECT
        DATE_TRUNC('month', order_date)                             AS order_month,
        COUNT(DISTINCT order_id)                                    AS total_orders,
        COUNT(DISTINCT customer_id)                                 AS unique_customers,
        SUM(sales)                                                  AS total_revenue,
        SUM(profit)                                                 AS total_profit,
        ROUND(SUM(profit) / NULLIF(SUM(sales), 0) * 100, 2)        AS margin_pct,
        SUM(quantity)                                               AS total_units
    FROM int_sales_enriched
    GROUP BY 1
)
SELECT
    order_month,
    total_orders,
    unique_customers,
    total_revenue,
    total_profit,
    margin_pct,
    total_units,
    LAG(total_revenue) OVER (ORDER BY order_month)                 AS prior_month_revenue,
    ROUND(
        (total_revenue - LAG(total_revenue) OVER (ORDER BY order_month))
        / NULLIF(LAG(total_revenue) OVER (ORDER BY order_month), 0) * 100,
        2
    )                                                               AS mom_growth_pct
FROM base
ORDER BY 1;


-- MART LAYER — business-ready tables for reporting

-- mart_exec_kpis: single-row headline KPIs
CREATE OR REPLACE VIEW mart_exec_kpis AS
SELECT
    ROUND(SUM(sales), 2)                                           AS total_revenue,
    ROUND(SUM(profit), 2)                                          AS total_profit,
    ROUND(SUM(profit) / NULLIF(SUM(sales), 0) * 100, 2)           AS overall_margin_pct,
    COUNT(DISTINCT order_id)                                       AS total_orders,
    COUNT(DISTINCT customer_id)                                    AS total_customers,
    MIN(order_date)                                                AS date_min,
    MAX(order_date)                                                AS date_max,
    ROUND(AVG(ship_days), 2)                                       AS avg_ship_days
FROM int_sales_enriched;


-- mart_regional_performance: by region and year with YoY growth and rank
CREATE OR REPLACE VIEW mart_regional_performance AS
WITH regional_yearly AS (
    SELECT
        region,
        order_year,
        ROUND(SUM(sales), 2)                                       AS total_revenue,
        ROUND(SUM(profit), 2)                                      AS total_profit,
        ROUND(SUM(profit) / NULLIF(SUM(sales), 0) * 100, 2)       AS margin_pct,
        COUNT(DISTINCT order_id)                                   AS total_orders,
        COUNT(DISTINCT customer_id)                                AS unique_customers
    FROM int_sales_enriched
    GROUP BY 1, 2
)
SELECT
    region,
    order_year,
    total_revenue,
    total_profit,
    margin_pct,
    total_orders,
    unique_customers,
    RANK() OVER (
        PARTITION BY order_year
        ORDER BY total_revenue DESC
    )                                                               AS revenue_rank,
    ROUND(
        (total_revenue - LAG(total_revenue) OVER (
            PARTITION BY region ORDER BY order_year
        )) / NULLIF(
            LAG(total_revenue) OVER (
                PARTITION BY region ORDER BY order_year
            ), 0
        ) * 100,
        2
    )                                                               AS yoy_growth
FROM regional_yearly
ORDER BY order_year, revenue_rank;


-- mart_product_performance: by category, sub-category, product with rank
CREATE OR REPLACE VIEW mart_product_performance AS
SELECT
    category,
    sub_category,
    product_name,
    ROUND(SUM(sales), 2)                                           AS total_revenue,
    ROUND(SUM(profit), 2)                                          AS total_profit,
    ROUND(SUM(profit) / NULLIF(SUM(sales), 0) * 100, 2)           AS margin_pct,
    SUM(quantity)                                                  AS total_units,
    RANK() OVER (
        PARTITION BY category
        ORDER BY SUM(sales) DESC
    )                                                               AS revenue_rank_in_category
FROM int_sales_enriched
GROUP BY 1, 2, 3
ORDER BY category, revenue_rank_in_category;


-- mart_segment_analysis: by segment and year
CREATE OR REPLACE VIEW mart_segment_analysis AS
SELECT
    segment,
    order_year,
    ROUND(SUM(sales), 2)                                           AS total_revenue,
    ROUND(SUM(profit), 2)                                          AS total_profit,
    ROUND(SUM(profit) / NULLIF(SUM(sales), 0) * 100, 2)           AS margin_pct,
    ROUND(SUM(sales) / NULLIF(COUNT(DISTINCT order_id), 0), 2)    AS avg_order_value,
    COUNT(DISTINCT customer_id)                                    AS total_customers
FROM int_sales_enriched
GROUP BY 1, 2
ORDER BY segment, order_year;


-- mart_state_performance: by state with overall revenue rank
CREATE OR REPLACE VIEW mart_state_performance AS
SELECT
    state,
    region,
    ROUND(SUM(sales), 2)                                           AS total_revenue,
    ROUND(SUM(profit), 2)                                          AS total_profit,
    ROUND(SUM(profit) / NULLIF(SUM(sales), 0) * 100, 2)           AS margin_pct,
    COUNT(DISTINCT order_id)                                       AS total_orders,
    RANK() OVER (ORDER BY SUM(sales) DESC)                         AS revenue_rank
FROM int_sales_enriched
GROUP BY 1, 2
ORDER BY revenue_rank;
