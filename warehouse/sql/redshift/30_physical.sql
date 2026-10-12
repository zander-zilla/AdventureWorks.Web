-- Redshift-only physical design for the star schema (kept out of the portable DDL).
-- Facts distributed on the biggest dimension they join to; small dims replicated (ALL); facts sorted by order date.
ALTER TABLE dw.fact_internet_sales ALTER DISTSTYLE KEY DISTKEY customer_key;
ALTER TABLE dw.fact_internet_sales ALTER COMPOUND SORTKEY (order_date_key, product_key);
ALTER TABLE dw.fact_reseller_sales ALTER DISTSTYLE KEY DISTKEY reseller_key;
ALTER TABLE dw.fact_reseller_sales ALTER COMPOUND SORTKEY (order_date_key, product_key);
ALTER TABLE dw.fact_product_inventory ALTER DISTSTYLE KEY DISTKEY product_key;
ALTER TABLE dw.fact_product_inventory ALTER COMPOUND SORTKEY (date_key, product_key);
ALTER TABLE dw.fact_internet_sales_reason ALTER DISTSTYLE EVEN;
ALTER TABLE dw.dim_customer ALTER DISTSTYLE KEY DISTKEY customer_key;
ALTER TABLE dw.dim_date ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_product ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_product_category ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_product_subcategory ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_promotion ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_sales_territory ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_currency ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_sales_reason ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_geography ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_reseller ALTER DISTSTYLE ALL;
ALTER TABLE dw.dim_employee ALTER DISTSTYLE ALL;
