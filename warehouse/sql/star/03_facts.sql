-- Facts. PORTABLE SQL (Redshift + Postgres). Measures follow AdventureWorksDW conventions:
--   extended_amount = qty * unit_price; discount_amount = extended * discount pct; sales_amount = SalesOrderDetail.LineTotal;
--   tax_amt / freight = header amount allocated to lines by line_total / sub_total; product_standard_cost = cost history at order date.
-- Dates are the real (replicated) order dates; AdventureWorksDW2022 ships shifted dates, so reconcile by order number/line.

-- Shared order-line working set (same for internet and reseller facts).
DROP TABLE IF EXISTS dw.wrk_sales_line;
CREATE TABLE dw.wrk_sales_line AS
SELECT h.sales_order_id, h.sales_order_number, h.online_order_flag, h.revision_number, h.order_date, h.due_date, h.ship_date,
       h.customer_id, h.sales_person_id, h.territory_id, h.purchase_order_number, h.currency_to, h.sub_total, h.tax_amt, h.freight,
       l.sales_order_detail_id, l.product_id, l.special_offer_id, l.order_qty, l.unit_price, l.unit_price_discount, l.line_total,
       l.carrier_tracking_number,
       CAST(ROW_NUMBER() OVER (PARTITION BY h.sales_order_id ORDER BY l.sales_order_detail_id) AS integer) AS line_number
FROM stg."order" h JOIN stg.order_line l ON l.sales_order_id = h.sales_order_id;

-- product version effective at the order date (latest version starting on/before it, else the first version)
DROP TABLE IF EXISTS dw.wrk_line_keys;
CREATE TABLE dw.wrk_line_keys AS
WITH pv AS (
  SELECT w.sales_order_id, w.sales_order_detail_id, dp.product_key,
         ROW_NUMBER() OVER (PARTITION BY w.sales_order_id, w.sales_order_detail_id
                            ORDER BY CASE WHEN dp.start_date <= w.order_date THEN 0 ELSE 1 END, dp.start_date DESC) AS rn
  FROM dw.wrk_sales_line w JOIN dw.dim_product dp ON dp.product_id = w.product_id),
pc AS (
  SELECT w.sales_order_id, w.sales_order_detail_id, c.standard_cost,
         ROW_NUMBER() OVER (PARTITION BY w.sales_order_id, w.sales_order_detail_id
                            ORDER BY CASE WHEN c.start_date <= w.order_date THEN 0 ELSE 1 END, c.start_date DESC) AS rn
  FROM dw.wrk_sales_line w JOIN stg.cost_history c ON c.product_id = w.product_id)
SELECT w.sales_order_id, w.sales_order_detail_id, pv.product_key, COALESCE(pc.standard_cost, p.standard_cost) AS standard_cost
FROM dw.wrk_sales_line w
LEFT JOIN pv ON pv.sales_order_id = w.sales_order_id AND pv.sales_order_detail_id = w.sales_order_detail_id AND pv.rn = 1
LEFT JOIN pc ON pc.sales_order_id = w.sales_order_id AND pc.sales_order_detail_id = w.sales_order_detail_id AND pc.rn = 1
LEFT JOIN stg.product p ON p.product_id = w.product_id;

DELETE FROM dw.fact_internet_sales;
INSERT INTO dw.fact_internet_sales
SELECT k.product_key, CAST(TO_CHAR(w.order_date, 'YYYYMMDD') AS integer), CAST(TO_CHAR(w.due_date, 'YYYYMMDD') AS integer),
       CAST(TO_CHAR(w.ship_date, 'YYYYMMDD') AS integer), w.customer_id, w.special_offer_id, cur.currency_key, w.territory_id,
       w.sales_order_number, w.line_number, w.revision_number, w.order_qty, w.unit_price,
       CAST(w.order_qty * w.unit_price AS decimal(19,4)), CAST(w.unit_price_discount AS double precision),
       CAST(w.order_qty * w.unit_price * w.unit_price_discount AS double precision),
       k.standard_cost, CAST(k.standard_cost * w.order_qty AS decimal(19,4)), CAST(w.line_total AS decimal(19,4)),
       CAST(CASE WHEN w.sub_total = 0 THEN 0 ELSE w.tax_amt * w.line_total / w.sub_total END AS decimal(19,4)),
       CAST(CASE WHEN w.sub_total = 0 THEN 0 ELSE w.freight * w.line_total / w.sub_total END AS decimal(19,4)),
       w.carrier_tracking_number, w.purchase_order_number, w.order_date, w.due_date, w.ship_date
FROM dw.wrk_sales_line w
JOIN dw.wrk_line_keys k ON k.sales_order_id = w.sales_order_id AND k.sales_order_detail_id = w.sales_order_detail_id
LEFT JOIN dw.dim_currency cur ON cur.currency_alternate_key = COALESCE(w.currency_to, 'USD')
WHERE w.online_order_flag = true;

DELETE FROM dw.fact_reseller_sales;
INSERT INTO dw.fact_reseller_sales
SELECT k.product_key, CAST(TO_CHAR(w.order_date, 'YYYYMMDD') AS integer), CAST(TO_CHAR(w.due_date, 'YYYYMMDD') AS integer),
       CAST(TO_CHAR(w.ship_date, 'YYYYMMDD') AS integer), r.reseller_key, emp.employee_key, w.special_offer_id, cur.currency_key,
       w.territory_id, w.sales_order_number, w.line_number, w.revision_number, w.order_qty, w.unit_price,
       CAST(w.order_qty * w.unit_price AS decimal(19,4)), CAST(w.unit_price_discount AS double precision),
       CAST(w.order_qty * w.unit_price * w.unit_price_discount AS double precision),
       k.standard_cost, CAST(k.standard_cost * w.order_qty AS decimal(19,4)), CAST(w.line_total AS decimal(19,4)),
       CAST(CASE WHEN w.sub_total = 0 THEN 0 ELSE w.tax_amt * w.line_total / w.sub_total END AS decimal(19,4)),
       CAST(CASE WHEN w.sub_total = 0 THEN 0 ELSE w.freight * w.line_total / w.sub_total END AS decimal(19,4)),
       w.carrier_tracking_number, w.purchase_order_number, w.order_date, w.due_date, w.ship_date
FROM dw.wrk_sales_line w
JOIN dw.wrk_line_keys k ON k.sales_order_id = w.sales_order_id AND k.sales_order_detail_id = w.sales_order_detail_id
JOIN stg.customer cu ON cu.customer_id = w.customer_id
LEFT JOIN dw.dim_reseller r ON r.store_id = cu.store_id
LEFT JOIN dw.dim_employee emp ON emp.business_entity_id = w.sales_person_id AND emp.status = 'Current'
LEFT JOIN dw.dim_currency cur ON cur.currency_alternate_key = COALESCE(w.currency_to, 'USD')
WHERE w.online_order_flag = false;

DELETE FROM dw.fact_internet_sales_reason;
INSERT INTO dw.fact_internet_sales_reason
SELECT w.sales_order_number, w.line_number, r.sales_reason_id
FROM dw.wrk_sales_line w JOIN stg.order_sales_reason r ON r.sales_order_id = w.sales_order_id
WHERE w.online_order_flag = true;

DELETE FROM dw.fact_sales_quota;
INSERT INTO dw.fact_sales_quota
SELECT CAST(ROW_NUMBER() OVER (ORDER BY q.business_entity_id, q.quota_date) AS integer), emp.employee_key,
       CAST(TO_CHAR(q.quota_date, 'YYYYMMDD') AS integer), CAST(EXTRACT(YEAR FROM q.quota_date) AS smallint),
       CAST((EXTRACT(MONTH FROM q.quota_date) - 1) / 3 + 1 AS smallint), q.sales_quota, q.quota_date
FROM stg.sales_quota q
LEFT JOIN dw.dim_employee emp ON emp.business_entity_id = q.business_entity_id AND emp.status = 'Current';

-- FactCurrencyRate: USD -> currency daily rates (one row per currency and day; last rate of the day wins)
DELETE FROM dw.fact_currency_rate;
INSERT INTO dw.fact_currency_rate
SELECT currency_key, date_key, average_rate, end_of_day_rate, currency_rate_date FROM (
  SELECT cur.currency_key, CAST(TO_CHAR(r.currency_rate_date, 'YYYYMMDD') AS integer) AS date_key,
         CAST(r.average_rate AS double precision) AS average_rate, CAST(r.end_of_day_rate AS double precision) AS end_of_day_rate,
         r.currency_rate_date, ROW_NUMBER() OVER (PARTITION BY r.to_currency_code, r.currency_rate_date ORDER BY r.currency_rate_id DESC) AS rn
  FROM stg.currency_rate r JOIN dw.dim_currency cur ON cur.currency_alternate_key = r.to_currency_code) x
WHERE rn = 1;

-- FactProductInventory: daily movements and running balance per product, rebuilt from inventory transactions
-- (current + archived). One row per product and day from the product's first movement to the last movement date in the data.
-- Balance is anchored so that the final balance equals the current on-hand quantity (sum of ProductInventory).
DROP TABLE IF EXISTS dw.wrk_inv_moves;
CREATE TABLE dw.wrk_inv_moves AS
SELECT product_id, CAST(transaction_date AS date) AS d,
       SUM(CASE WHEN transaction_type IN ('P', 'W') THEN quantity ELSE 0 END) AS units_in,
       SUM(CASE WHEN transaction_type = 'S' THEN quantity ELSE 0 END) AS units_out,
       MAX(CASE WHEN src = 'ddb' THEN 1 ELSE 0 END) AS app
FROM stg.inventory_transaction GROUP BY product_id, CAST(transaction_date AS date);

DELETE FROM dw.fact_product_inventory;
INSERT INTO dw.fact_product_inventory
WITH span AS (SELECT product_id, MIN(d) AS first_d FROM dw.wrk_inv_moves GROUP BY product_id),
-- C2-2: the daily grid is continuous up to the last migrated (SQL-era) movement; app movements (src = ddb, years later)
-- add only their own product/day rows, so one shipment in 2026 does not add 12 years x 500 products of empty days.
last_d AS (SELECT MAX(d) AS d FROM dw.wrk_inv_moves WHERE app = 0),
grid AS (SELECT s.product_id, dd.full_date AS d, dd.date_key
         FROM span s CROSS JOIN last_d ld JOIN dw.dim_date dd ON dd.full_date >= s.first_d AND dd.full_date <= ld.d
         UNION
         SELECT m.product_id, dd.full_date, dd.date_key
         FROM dw.wrk_inv_moves m CROSS JOIN last_d ld JOIN dw.dim_date dd ON dd.full_date = m.d WHERE m.d > ld.d),
onhand AS (SELECT product_id, SUM(quantity) AS qty FROM stg.product_inventory GROUP BY product_id),
net AS (SELECT product_id, SUM(units_in - units_out) AS total FROM dw.wrk_inv_moves GROUP BY product_id),
pv AS (SELECT g.product_id, g.d, dp.product_key, dp.standard_cost,
              ROW_NUMBER() OVER (PARTITION BY g.product_id, g.d ORDER BY CASE WHEN dp.start_date <= g.d THEN 0 ELSE 1 END, dp.start_date DESC) AS rn
       FROM grid g JOIN dw.dim_product dp ON dp.product_id = g.product_id)
SELECT pv.product_key, g.date_key, g.d, pv.standard_cost, COALESCE(m.units_in, 0), COALESCE(m.units_out, 0),
       CAST(COALESCE(oh.qty, 0) - n.total
            + SUM(COALESCE(m.units_in, 0) - COALESCE(m.units_out, 0)) OVER (PARTITION BY g.product_id ORDER BY g.d ROWS UNBOUNDED PRECEDING) AS integer)
FROM grid g
JOIN pv ON pv.product_id = g.product_id AND pv.d = g.d AND pv.rn = 1
JOIN net n ON n.product_id = g.product_id
LEFT JOIN onhand oh ON oh.product_id = g.product_id
LEFT JOIN dw.wrk_inv_moves m ON m.product_id = g.product_id AND m.d = g.d;

DROP TABLE dw.wrk_sales_line;
DROP TABLE dw.wrk_line_keys;
DROP TABLE dw.wrk_inv_moves;
-- C2-3 FactPurchaseOrderLine: one row per PO line (Purchasing.PurchaseOrderDetail + header), SQL-era and app POs.
-- on_time_flag: 1 when the PO shipped (app: first receipt) on or before the line due date, 0 when later, NULL when not shipped.
-- Product version effective at the order date, as for the sales facts; employee = current DimEmployee row of the buyer.
DELETE FROM dw.fact_purchase_order_line;
INSERT INTO dw.fact_purchase_order_line
WITH pv AS (
  SELECT l.purchase_order_id, l.purchase_order_detail_id, dp.product_key,
         ROW_NUMBER() OVER (PARTITION BY l.purchase_order_id, l.purchase_order_detail_id
                            ORDER BY CASE WHEN dp.start_date <= h.order_date THEN 0 ELSE 1 END, dp.start_date DESC) AS rn
  FROM stg.purchase_order_line l JOIN stg.purchase_order h ON h.purchase_order_id = l.purchase_order_id
  JOIN dw.dim_product dp ON dp.product_id = l.product_id)
SELECT pv.product_key, h.vendor_id, emp.employee_key, CAST(TO_CHAR(h.order_date, 'YYYYMMDD') AS integer),
       CAST(TO_CHAR(l.due_date, 'YYYYMMDD') AS integer), CAST(TO_CHAR(h.ship_date, 'YYYYMMDD') AS integer),
       l.purchase_order_id, l.purchase_order_detail_id,
       CASE WHEN l.purchase_order_id >= 100000 THEN 'PO-DDB-' || CAST(l.purchase_order_id AS varchar(12))
            ELSE 'PO' || LPAD(CAST(l.purchase_order_id AS varchar(12)), 6, '0') END,
       h.status, h.revision_number, l.order_qty, l.unit_price, l.line_total,
       l.received_qty, l.rejected_qty, l.stocked_qty,
       CASE WHEN h.ship_date IS NULL OR l.due_date IS NULL THEN NULL
            WHEN CAST(h.ship_date AS date) <= CAST(l.due_date AS date) THEN 1 ELSE 0 END,
       CASE WHEN h.ship_date IS NULL THEN NULL ELSE CAST(CAST(h.ship_date AS date) - CAST(h.order_date AS date) AS integer) END,
       COALESCE(h.src, 'sql'), h.order_date, l.due_date, h.ship_date
FROM stg.purchase_order_line l
JOIN stg.purchase_order h ON h.purchase_order_id = l.purchase_order_id
LEFT JOIN pv ON pv.purchase_order_id = l.purchase_order_id AND pv.purchase_order_detail_id = l.purchase_order_detail_id AND pv.rn = 1
LEFT JOIN dw.dim_employee emp ON emp.business_entity_id = h.employee_id AND emp.status = 'Current';

-- C2-4 FactWorkOrder: one row per work order. AdventureWorks has no status column: closed = EndDate set; on time = closed and
-- EndDate <= DueDate (by day); days late = EndDate - DueDate when late. product_key = the dim_product version at the start date.
DELETE FROM dw.fact_work_order;
INSERT INTO dw.fact_work_order
WITH pv AS (
  SELECT w.work_order_id, dp.product_key,
         ROW_NUMBER() OVER (PARTITION BY w.work_order_id
                            ORDER BY CASE WHEN dp.start_date <= w.start_date THEN 0 ELSE 1 END, dp.start_date DESC) AS rn
  FROM stg.work_order w JOIN dw.dim_product dp ON dp.product_id = w.product_id)
SELECT pv.product_key, w.scrap_reason_id, CAST(TO_CHAR(w.start_date, 'YYYYMMDD') AS integer), CAST(TO_CHAR(w.end_date, 'YYYYMMDD') AS integer),
       CAST(TO_CHAR(w.due_date, 'YYYYMMDD') AS integer), w.work_order_id,
       CASE WHEN w.work_order_id >= 100000 THEN 'WO-DDB-' || CAST(w.work_order_id AS varchar(12))
            ELSE 'WO' || LPAD(CAST(w.work_order_id AS varchar(12)), 6, '0') END,
       w.order_qty, w.stocked_qty, w.scrapped_qty,
       CASE WHEN w.end_date IS NULL THEN 0 ELSE 1 END,
       CASE WHEN w.end_date IS NULL THEN NULL WHEN CAST(w.end_date AS date) <= CAST(w.due_date AS date) THEN 1 ELSE 0 END,
       CASE WHEN w.end_date IS NULL OR CAST(w.end_date AS date) <= CAST(w.due_date AS date) THEN 0
            ELSE CAST(CAST(w.end_date AS date) - CAST(w.due_date AS date) AS integer) END,
       COALESCE(w.src, 'sql'), w.start_date, w.end_date, w.due_date
FROM stg.work_order w
LEFT JOIN pv ON pv.work_order_id = w.work_order_id AND pv.rn = 1;

-- C2-4 FactWorkOrderRouting: one row per routing step; late = actual end after scheduled end.
DELETE FROM dw.fact_work_order_routing;
INSERT INTO dw.fact_work_order_routing
SELECT f.product_key, r.location_id, CAST(TO_CHAR(r.scheduled_start_date, 'YYYYMMDD') AS integer), CAST(TO_CHAR(r.scheduled_end_date, 'YYYYMMDD') AS integer),
       CAST(TO_CHAR(r.actual_start_date, 'YYYYMMDD') AS integer), CAST(TO_CHAR(r.actual_end_date, 'YYYYMMDD') AS integer),
       r.work_order_id, r.operation_sequence, r.actual_resource_hrs, r.planned_cost, r.actual_cost,
       CASE WHEN r.actual_end_date IS NULL THEN NULL WHEN r.actual_end_date > r.scheduled_end_date THEN 1 ELSE 0 END,
       COALESCE(r.src, 'sql')
FROM stg.work_order_routing r
LEFT JOIN dw.fact_work_order f ON f.work_order_id = r.work_order_id;

