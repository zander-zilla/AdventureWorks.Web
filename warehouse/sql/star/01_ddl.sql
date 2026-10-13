-- AdventureWorksDW star schema rebuilt from the DynamoDB domain tables (phase 6).
-- PORTABLE SQL: runs unchanged on Amazon Redshift and on the local Postgres stand-in (CI). Keep to the subset
-- checked by tests/warehouse/test_portable_sql.py. Redshift-only physical design (DISTKEY/SORTKEY) is in
-- warehouse/sql/redshift/30_physical.sql. Names: snake_case of the AdventureWorksDW2022 names (see docs/design/warehouse.md).
CREATE SCHEMA IF NOT EXISTS dw;
DROP VIEW IF EXISTS dw.v_sales;
DROP VIEW IF EXISTS dw.v_vendor_performance;
DROP VIEW IF EXISTS dw.v_production_scrap_on_time;

DROP TABLE IF EXISTS dw.dim_date;
CREATE TABLE dw.dim_date (
  date_key integer NOT NULL, full_date date NOT NULL, day_number_of_week smallint, english_day_name_of_week varchar(10),
  spanish_day_name_of_week varchar(10), french_day_name_of_week varchar(10), day_number_of_month smallint, day_number_of_year smallint,
  week_number_of_year smallint, english_month_name varchar(10), spanish_month_name varchar(10), french_month_name varchar(10),
  month_number_of_year smallint, calendar_quarter smallint, calendar_year smallint, calendar_semester smallint,
  fiscal_quarter smallint, fiscal_year smallint, fiscal_semester smallint, PRIMARY KEY (date_key));

DROP TABLE IF EXISTS dw.dim_sales_territory;
CREATE TABLE dw.dim_sales_territory (
  sales_territory_key integer NOT NULL, sales_territory_alternate_key integer, sales_territory_region varchar(50),
  sales_territory_country varchar(50), sales_territory_group varchar(50), PRIMARY KEY (sales_territory_key));

DROP TABLE IF EXISTS dw.dim_currency;
CREATE TABLE dw.dim_currency (currency_key integer NOT NULL, currency_alternate_key varchar(3), currency_name varchar(50), PRIMARY KEY (currency_key));

DROP TABLE IF EXISTS dw.dim_sales_reason;
CREATE TABLE dw.dim_sales_reason (sales_reason_key integer NOT NULL, sales_reason_alternate_key integer, sales_reason_name varchar(50),
  sales_reason_reason_type varchar(50), PRIMARY KEY (sales_reason_key));

DROP TABLE IF EXISTS dw.dim_product_category;
CREATE TABLE dw.dim_product_category (product_category_key integer NOT NULL, product_category_alternate_key integer,
  english_product_category_name varchar(50), spanish_product_category_name varchar(50), french_product_category_name varchar(50),
  PRIMARY KEY (product_category_key));

DROP TABLE IF EXISTS dw.dim_product_subcategory;
CREATE TABLE dw.dim_product_subcategory (product_subcategory_key integer NOT NULL, product_subcategory_alternate_key integer,
  english_product_subcategory_name varchar(50), spanish_product_subcategory_name varchar(50), french_product_subcategory_name varchar(50),
  product_category_key integer, PRIMARY KEY (product_subcategory_key));

DROP TABLE IF EXISTS dw.dim_promotion;
CREATE TABLE dw.dim_promotion (promotion_key integer NOT NULL, promotion_alternate_key integer, english_promotion_name varchar(255),
  spanish_promotion_name varchar(255), french_promotion_name varchar(255), discount_pct decimal(19,4), english_promotion_type varchar(50),
  spanish_promotion_type varchar(50), french_promotion_type varchar(50), english_promotion_category varchar(50),
  spanish_promotion_category varchar(50), french_promotion_category varchar(50), start_date timestamp, end_date timestamp,
  min_qty integer, max_qty integer, PRIMARY KEY (promotion_key));

DROP TABLE IF EXISTS dw.dim_geography;
CREATE TABLE dw.dim_geography (geography_key integer NOT NULL, city varchar(30), state_province_code varchar(3), state_province_name varchar(50),
  country_region_code varchar(3), english_country_region_name varchar(50), spanish_country_region_name varchar(50),
  french_country_region_name varchar(50), postal_code varchar(15), sales_territory_key integer, PRIMARY KEY (geography_key));

DROP TABLE IF EXISTS dw.dim_customer;
CREATE TABLE dw.dim_customer (customer_key integer NOT NULL, geography_key integer, customer_alternate_key varchar(15), title varchar(8),
  first_name varchar(50), middle_name varchar(50), last_name varchar(50), name_style boolean, birth_date date, marital_status varchar(1),
  suffix varchar(10), gender varchar(1), email_address varchar(50), yearly_income decimal(19,4), total_children smallint,
  number_children_at_home smallint, english_education varchar(40), english_occupation varchar(100), house_owner_flag varchar(1),
  number_cars_owned smallint, address_line1 varchar(120), address_line2 varchar(120), phone varchar(25), date_first_purchase date,
  commute_distance varchar(15), PRIMARY KEY (customer_key));

DROP TABLE IF EXISTS dw.dim_reseller;
CREATE TABLE dw.dim_reseller (reseller_key integer NOT NULL, geography_key integer, reseller_alternate_key varchar(15), business_type varchar(20),
  reseller_name varchar(50), number_employees integer, product_line varchar(50), address_line1 varchar(60), address_line2 varchar(60),
  annual_sales decimal(19,4), bank_name varchar(50), annual_revenue decimal(19,4), year_opened integer,
  store_id integer, PRIMARY KEY (reseller_key));

DROP TABLE IF EXISTS dw.dim_product;
CREATE TABLE dw.dim_product (product_key integer NOT NULL, product_alternate_key varchar(25), product_subcategory_key integer,
  weight_unit_measure_code varchar(3), size_unit_measure_code varchar(3), english_product_name varchar(50), spanish_product_name varchar(50),
  french_product_name varchar(50), standard_cost decimal(19,4), finished_goods_flag boolean, color varchar(15), safety_stock_level smallint,
  reorder_point smallint, list_price decimal(19,4), size varchar(50), weight double precision, days_to_manufacture integer,
  product_line varchar(2), dealer_price decimal(19,4), class varchar(2), style varchar(2), model_name varchar(50),
  english_description varchar(400), french_description varchar(400), start_date timestamp, end_date timestamp, status varchar(7),
  product_id integer, PRIMARY KEY (product_key));

DROP TABLE IF EXISTS dw.dim_employee;
CREATE TABLE dw.dim_employee (employee_key integer NOT NULL, parent_employee_key integer, employee_national_id_alternate_key varchar(15),
  parent_employee_national_id_alternate_key varchar(15), sales_territory_key integer, first_name varchar(50), last_name varchar(50),
  middle_name varchar(50), name_style boolean, title varchar(50), hire_date date, birth_date date, login_id varchar(256),
  email_address varchar(50), phone varchar(25), marital_status varchar(1), salaried_flag boolean, gender varchar(1),
  pay_frequency smallint, base_rate decimal(19,4), vacation_hours smallint, sick_leave_hours smallint, current_flag boolean,
  sales_person_flag boolean, department_name varchar(50), start_date date, end_date date, status varchar(50),
  business_entity_id integer, PRIMARY KEY (employee_key));

DROP TABLE IF EXISTS dw.fact_internet_sales;
CREATE TABLE dw.fact_internet_sales (product_key integer, order_date_key integer, due_date_key integer, ship_date_key integer,
  customer_key integer, promotion_key integer, currency_key integer, sales_territory_key integer, sales_order_number varchar(20) NOT NULL,
  sales_order_line_number smallint NOT NULL, revision_number smallint, order_quantity smallint, unit_price decimal(19,4),
  extended_amount decimal(19,4), unit_price_discount_pct double precision, discount_amount double precision,
  product_standard_cost decimal(19,4), total_product_cost decimal(19,4), sales_amount decimal(19,4), tax_amt decimal(19,4),
  freight decimal(19,4), carrier_tracking_number varchar(25), customer_po_number varchar(25), order_date timestamp, due_date timestamp,
  ship_date timestamp, PRIMARY KEY (sales_order_number, sales_order_line_number));

DROP TABLE IF EXISTS dw.fact_reseller_sales;
CREATE TABLE dw.fact_reseller_sales (product_key integer, order_date_key integer, due_date_key integer, ship_date_key integer,
  reseller_key integer, employee_key integer, promotion_key integer, currency_key integer, sales_territory_key integer,
  sales_order_number varchar(20) NOT NULL, sales_order_line_number smallint NOT NULL, revision_number smallint, order_quantity smallint,
  unit_price decimal(19,4), extended_amount decimal(19,4), unit_price_discount_pct double precision, discount_amount double precision,
  product_standard_cost decimal(19,4), total_product_cost decimal(19,4), sales_amount decimal(19,4), tax_amt decimal(19,4),
  freight decimal(19,4), carrier_tracking_number varchar(25), customer_po_number varchar(25), order_date timestamp, due_date timestamp,
  ship_date timestamp, PRIMARY KEY (sales_order_number, sales_order_line_number));

DROP TABLE IF EXISTS dw.fact_internet_sales_reason;
CREATE TABLE dw.fact_internet_sales_reason (sales_order_number varchar(20) NOT NULL, sales_order_line_number smallint NOT NULL,
  sales_reason_key integer NOT NULL, PRIMARY KEY (sales_order_number, sales_order_line_number, sales_reason_key));

DROP TABLE IF EXISTS dw.fact_sales_quota;
CREATE TABLE dw.fact_sales_quota (sales_quota_key integer NOT NULL, employee_key integer, date_key integer, calendar_year smallint,
  calendar_quarter smallint, sales_amount_quota decimal(19,4), date timestamp, PRIMARY KEY (sales_quota_key));

DROP TABLE IF EXISTS dw.fact_currency_rate;
CREATE TABLE dw.fact_currency_rate (currency_key integer NOT NULL, date_key integer NOT NULL, average_rate double precision,
  end_of_day_rate double precision, date timestamp, PRIMARY KEY (currency_key, date_key));

DROP TABLE IF EXISTS dw.fact_product_inventory;
CREATE TABLE dw.fact_product_inventory (product_key integer NOT NULL, date_key integer NOT NULL, movement_date date, unit_cost decimal(19,4),
  units_in integer, units_out integer, units_balance integer, PRIMARY KEY (product_key, date_key));

-- C2-3 procurement (no AdventureWorksDW2022 equivalent: the DW has no purchasing fact). DimVendor is Purchasing.Vendor.
-- FactPurchaseOrderLine is one row per PurchaseOrderDetail (SQL-era and app-written POs alike, src tells them apart).
DROP TABLE IF EXISTS dw.dim_vendor;
CREATE TABLE dw.dim_vendor (vendor_key integer NOT NULL, vendor_alternate_key varchar(15), vendor_name varchar(50), credit_rating smallint,
  preferred_vendor_flag boolean, active_flag boolean, PRIMARY KEY (vendor_key));

DROP TABLE IF EXISTS dw.fact_purchase_order_line;
CREATE TABLE dw.fact_purchase_order_line (product_key integer, vendor_key integer, employee_key integer, order_date_key integer,
  due_date_key integer, ship_date_key integer, purchase_order_id integer NOT NULL, purchase_order_detail_id integer NOT NULL,
  purchase_order_number varchar(20), status smallint, revision_number smallint, order_quantity integer, unit_price decimal(19,4),
  line_total decimal(19,4), received_quantity decimal(19,4), rejected_quantity decimal(19,4), stocked_quantity decimal(19,4),
  on_time_flag smallint, lead_time_days integer, source varchar(8), order_date timestamp, due_date timestamp, ship_date timestamp,
  PRIMARY KEY (purchase_order_id, purchase_order_detail_id));

-- C2-4 production floor (no AdventureWorksDW2022 equivalent: the DW has no manufacturing fact). DimScrapReason and DimLocation
-- are Production.ScrapReason / Production.Location. FactWorkOrder is one row per WorkOrder, FactWorkOrderRouting one row per
-- WorkOrderRouting step (SQL-era and app-written work orders alike, source tells them apart).
DROP TABLE IF EXISTS dw.dim_scrap_reason;
CREATE TABLE dw.dim_scrap_reason (scrap_reason_key integer NOT NULL, scrap_reason_name varchar(50), PRIMARY KEY (scrap_reason_key));

DROP TABLE IF EXISTS dw.dim_location;
CREATE TABLE dw.dim_location (location_key integer NOT NULL, location_name varchar(50), cost_rate decimal(10,4), availability decimal(8,2),
  PRIMARY KEY (location_key));

DROP TABLE IF EXISTS dw.fact_work_order;
CREATE TABLE dw.fact_work_order (product_key integer, scrap_reason_key integer, start_date_key integer, end_date_key integer, due_date_key integer,
  work_order_id integer NOT NULL, work_order_number varchar(20), order_quantity integer, stocked_quantity integer, scrapped_quantity integer,
  closed_flag smallint, on_time_flag smallint, days_late integer, source varchar(8), start_date timestamp, end_date timestamp, due_date timestamp,
  PRIMARY KEY (work_order_id));

DROP TABLE IF EXISTS dw.fact_work_order_routing;
CREATE TABLE dw.fact_work_order_routing (product_key integer, location_key integer, scheduled_start_date_key integer, scheduled_end_date_key integer,
  actual_start_date_key integer, actual_end_date_key integer, work_order_id integer NOT NULL, operation_sequence smallint NOT NULL,
  actual_resource_hrs decimal(9,4), planned_cost decimal(19,4), actual_cost decimal(19,4), late_flag smallint, source varchar(8),
  PRIMARY KEY (work_order_id, operation_sequence, location_key));

