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
