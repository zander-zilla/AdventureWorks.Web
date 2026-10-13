-- Reporting views for QuickSight (PORTABLE SQL). One wide sales view across both channels.
DROP VIEW IF EXISTS dw.v_sales;
CREATE VIEW dw.v_sales AS
SELECT 'Internet' AS channel, f.sales_order_number, f.sales_order_line_number, f.order_date, d.calendar_year, d.calendar_quarter,
       d.month_number_of_year, d.english_month_name, d.fiscal_year, t.sales_territory_group, t.sales_territory_country, t.sales_territory_region,
       pc.english_product_category_name AS product_category, ps.english_product_subcategory_name AS product_subcategory,
       p.english_product_name AS product_name, p.model_name, pr.english_promotion_name AS promotion,
       c.first_name || ' ' || c.last_name AS customer_or_reseller, f.order_quantity, f.sales_amount, f.total_product_cost,
       f.sales_amount - f.total_product_cost AS gross_margin, f.tax_amt, f.freight
FROM dw.fact_internet_sales f
JOIN dw.dim_date d ON d.date_key = f.order_date_key
LEFT JOIN dw.dim_sales_territory t ON t.sales_territory_key = f.sales_territory_key
LEFT JOIN dw.dim_product p ON p.product_key = f.product_key
LEFT JOIN dw.dim_product_subcategory ps ON ps.product_subcategory_key = p.product_subcategory_key
LEFT JOIN dw.dim_product_category pc ON pc.product_category_key = ps.product_category_key
LEFT JOIN dw.dim_promotion pr ON pr.promotion_key = f.promotion_key
LEFT JOIN dw.dim_customer c ON c.customer_key = f.customer_key
UNION ALL
SELECT 'Reseller', f.sales_order_number, f.sales_order_line_number, f.order_date, d.calendar_year, d.calendar_quarter,
       d.month_number_of_year, d.english_month_name, d.fiscal_year, t.sales_territory_group, t.sales_territory_country, t.sales_territory_region,
       pc.english_product_category_name, ps.english_product_subcategory_name, p.english_product_name, p.model_name, pr.english_promotion_name,
       r.reseller_name, f.order_quantity, f.sales_amount, f.total_product_cost, f.sales_amount - f.total_product_cost, f.tax_amt, f.freight
FROM dw.fact_reseller_sales f
JOIN dw.dim_date d ON d.date_key = f.order_date_key
LEFT JOIN dw.dim_sales_territory t ON t.sales_territory_key = f.sales_territory_key
LEFT JOIN dw.dim_product p ON p.product_key = f.product_key
LEFT JOIN dw.dim_product_subcategory ps ON ps.product_subcategory_key = p.product_subcategory_key
LEFT JOIN dw.dim_product_category pc ON pc.product_category_key = ps.product_category_key
LEFT JOIN dw.dim_promotion pr ON pr.promotion_key = f.promotion_key
LEFT JOIN dw.dim_reseller r ON r.reseller_key = f.reseller_key;

-- C2-3 vendor performance (John's decision 5): the same definitions as the app's vendor page (ProcurementRepository.Performance):
-- reject rate = rejected / received; fill rate = received / ordered; on time = share of shipped lines with on_time_flag = 1.
-- spend = line totals of approved (2) and complete (4) POs; average lead = order -> ship days per PO.
DROP VIEW IF EXISTS dw.v_vendor_performance;
CREATE VIEW dw.v_vendor_performance AS
SELECT v.vendor_key, v.vendor_name, v.preferred_vendor_flag, v.credit_rating,
       COUNT(DISTINCT f.purchase_order_id) AS purchase_orders, COUNT(*) AS lines,
       SUM(f.order_quantity) AS ordered_quantity, SUM(f.received_quantity) AS received_quantity, SUM(f.rejected_quantity) AS rejected_quantity,
       SUM(CASE WHEN f.status IN (2, 4) THEN f.line_total ELSE 0 END) AS spend,
       CASE WHEN SUM(f.received_quantity) = 0 THEN NULL ELSE CAST(SUM(f.rejected_quantity) AS double precision) / CAST(SUM(f.received_quantity) AS double precision) END AS reject_rate,
       CASE WHEN SUM(f.order_quantity) = 0 THEN NULL ELSE CAST(SUM(f.received_quantity) AS double precision) / CAST(SUM(f.order_quantity) AS double precision) END AS fill_rate,
       CASE WHEN COUNT(f.on_time_flag) = 0 THEN NULL ELSE CAST(SUM(f.on_time_flag) AS double precision) / CAST(COUNT(f.on_time_flag) AS double precision) END AS on_time_rate,
       AVG(CAST(f.lead_time_days AS double precision)) AS avg_lead_time_days,
       SUM(CASE WHEN f.source = 'ddb' THEN 1 ELSE 0 END) AS app_lines
FROM dw.fact_purchase_order_line f
JOIN dw.dim_vendor v ON v.vendor_key = f.vendor_key
GROUP BY v.vendor_key, v.vendor_name, v.preferred_vendor_flag, v.credit_rating;

-- C2-4 scrap and on-time production (John's decision 5), by due month: the same definitions as the app's production floor
-- (ProductionRepository.Kpis): scrap rate = scrapped / ordered; on time = closed with end date <= due date / closed.
DROP VIEW IF EXISTS dw.v_production_scrap_on_time;
CREATE VIEW dw.v_production_scrap_on_time AS
SELECT d.calendar_year, d.month_number_of_year, CAST(f.due_date_key / 100 AS integer) AS due_year_month,
       COUNT(*) AS work_orders, SUM(f.closed_flag) AS closed, SUM(COALESCE(f.on_time_flag, 0)) AS on_time,
       SUM(f.order_quantity) AS order_quantity, SUM(f.scrapped_quantity) AS scrapped_quantity,
       CASE WHEN SUM(f.order_quantity) = 0 THEN NULL ELSE CAST(SUM(f.scrapped_quantity) AS double precision) / CAST(SUM(f.order_quantity) AS double precision) END AS scrap_rate,
       CASE WHEN SUM(f.closed_flag) = 0 THEN NULL ELSE CAST(SUM(COALESCE(f.on_time_flag, 0)) AS double precision) / CAST(SUM(f.closed_flag) AS double precision) END AS on_time_rate,
       SUM(CASE WHEN f.source = 'ddb' THEN 1 ELSE 0 END) AS app_work_orders
FROM dw.fact_work_order f
JOIN dw.dim_date d ON d.date_key = f.due_date_key
GROUP BY d.calendar_year, d.month_number_of_year, CAST(f.due_date_key / 100 AS integer);

