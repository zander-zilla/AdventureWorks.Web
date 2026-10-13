-- Dimensions. PORTABLE SQL (Redshift + Postgres). Each block is DELETE + INSERT ... SELECT so the whole build can run
-- inside one Redshift stored procedure transaction (TRUNCATE would commit implicitly).
-- Inputs: stg.* (typed views over the zero-ETL landing) and dw_static.loc_* (static localised names, decision 3).

-- DimDate: generated, 2005-01-01 .. 2014-12-31 (3,652 days, same range as AdventureWorksDW2022; C2-2: up to the end of
-- the year of the latest order when app orders exist); FY starts 1 July and is
-- named by the calendar year it starts in (FY2012 = Jul 2012 - Jun 2013), the convention AdventureWorksDW2022 uses from 2011 on.
DELETE FROM dw.dim_date;
INSERT INTO dw.dim_date
WITH d10 AS (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5
             UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9),
nums AS (SELECT a.n + 10 * b.n + 100 * c.n + 1000 * e.n AS n FROM d10 a CROSS JOIN d10 b CROSS JOIN d10 c CROSS JOIN d10 e),
-- C2-2: extends past 2014 to the end of the latest order year once the app writes orders (2026); unchanged otherwise.
lim AS (SELECT CAST(GREATEST(DATE '2014-12-31', COALESCE(CAST(TO_CHAR(MAX(o.due_date), 'YYYY') || '-12-31' AS date), DATE '2014-12-31'))
               - DATE '2005-01-01' AS integer) AS n_last FROM stg.order o),
days AS (SELECT CAST(DATE '2005-01-01' + n AS date) AS d FROM nums CROSS JOIN lim WHERE n <= lim.n_last),
p AS (SELECT d, CAST(EXTRACT(DOW FROM d) AS integer) AS dow, CAST(EXTRACT(DOY FROM d) AS integer) AS doy,
             CAST(EXTRACT(MONTH FROM d) AS integer) AS m, CAST(EXTRACT(YEAR FROM d) AS integer) AS y, CAST(EXTRACT(DAY FROM d) AS integer) AS dom
      FROM days)
SELECT CAST(TO_CHAR(d, 'YYYYMMDD') AS integer), d, dow + 1,
  CASE dow WHEN 0 THEN 'Sunday' WHEN 1 THEN 'Monday' WHEN 2 THEN 'Tuesday' WHEN 3 THEN 'Wednesday' WHEN 4 THEN 'Thursday' WHEN 5 THEN 'Friday' ELSE 'Saturday' END,
  CASE dow WHEN 0 THEN 'Domingo' WHEN 1 THEN 'Lunes' WHEN 2 THEN 'Martes' WHEN 3 THEN 'Miércoles' WHEN 4 THEN 'Jueves' WHEN 5 THEN 'Viernes' ELSE 'Sábado' END,
  CASE dow WHEN 0 THEN 'Dimanche' WHEN 1 THEN 'Lundi' WHEN 2 THEN 'Mardi' WHEN 3 THEN 'Mercredi' WHEN 4 THEN 'Jeudi' WHEN 5 THEN 'Vendredi' ELSE 'Samedi' END,
  dom, doy,
  -- week 1 contains 1 January, weeks start on Sunday (AdventureWorksDW convention)
  (doy - 1 + CAST(EXTRACT(DOW FROM CAST(d - (doy - 1) AS date)) AS integer)) / 7 + 1,
  CASE m WHEN 1 THEN 'January' WHEN 2 THEN 'February' WHEN 3 THEN 'March' WHEN 4 THEN 'April' WHEN 5 THEN 'May' WHEN 6 THEN 'June'
         WHEN 7 THEN 'July' WHEN 8 THEN 'August' WHEN 9 THEN 'September' WHEN 10 THEN 'October' WHEN 11 THEN 'November' ELSE 'December' END,
  CASE m WHEN 1 THEN 'Enero' WHEN 2 THEN 'Febrero' WHEN 3 THEN 'Marzo' WHEN 4 THEN 'Abril' WHEN 5 THEN 'Mayo' WHEN 6 THEN 'Junio'
         WHEN 7 THEN 'Julio' WHEN 8 THEN 'Agosto' WHEN 9 THEN 'Septiembre' WHEN 10 THEN 'Octubre' WHEN 11 THEN 'Noviembre' ELSE 'Diciembre' END,
  CASE m WHEN 1 THEN 'Janvier' WHEN 2 THEN 'Février' WHEN 3 THEN 'Mars' WHEN 4 THEN 'Avril' WHEN 5 THEN 'Mai' WHEN 6 THEN 'Juin'
         WHEN 7 THEN 'Juillet' WHEN 8 THEN 'Août' WHEN 9 THEN 'Septembre' WHEN 10 THEN 'Octobre' WHEN 11 THEN 'Novembre' ELSE 'Décembre' END,
  m, (m - 1) / 3 + 1, y, CASE WHEN m <= 6 THEN 1 ELSE 2 END,
  ((m + 5) % 12) / 3 + 1, CASE WHEN m >= 7 THEN y ELSE y - 1 END, CASE WHEN m >= 7 THEN 1 ELSE 2 END
FROM p;

DELETE FROM dw.dim_sales_territory;
INSERT INTO dw.dim_sales_territory
SELECT t.territory_id, t.territory_id, t.name, c.name, t."group"
FROM stg.sales_territory t LEFT JOIN stg.country c ON c.country_region_code = t.country_region_code
UNION ALL SELECT 11, 0, 'NA', 'NA', 'NA';

DELETE FROM dw.dim_currency;
INSERT INTO dw.dim_currency
SELECT CAST(ROW_NUMBER() OVER (ORDER BY currency_code) AS integer), currency_code, name FROM stg.currency;

DELETE FROM dw.dim_sales_reason;
INSERT INTO dw.dim_sales_reason SELECT sales_reason_id, sales_reason_id, name, reason_type FROM stg.sales_reason;

DELETE FROM dw.dim_product_category;
INSERT INTO dw.dim_product_category
SELECT c.product_category_id, c.product_category_id, c.name, l.spanish_name, l.french_name
FROM stg.category c LEFT JOIN dw_static.loc_product_category l ON l.alternate_key = c.product_category_id;

DELETE FROM dw.dim_product_subcategory;
INSERT INTO dw.dim_product_subcategory
SELECT s.product_subcategory_id, s.product_subcategory_id, s.name, l.spanish_name, l.french_name, s.product_category_id
FROM stg.subcategory s LEFT JOIN dw_static.loc_product_subcategory l ON l.alternate_key = s.product_subcategory_id;

DELETE FROM dw.dim_promotion;
INSERT INTO dw.dim_promotion
SELECT o.special_offer_id, o.special_offer_id, o.description, l.spanish_name, l.french_name, o.discount_pct,
       o.sql_type, l.spanish_type, l.french_type, o.category, l.spanish_category, l.french_category,
       o.start_date, o.end_date, o.min_qty, o.max_qty
FROM stg.special_offer o LEFT JOIN dw_static.loc_promotion l ON l.alternate_key = o.special_offer_id;

-- DimGeography: distinct city/state/postal code of the home addresses of individual customers and the
-- main-office addresses of resellers (the addresses DimCustomer/DimReseller point at).
DELETE FROM dw.dim_geography;
INSERT INTO dw.dim_geography
WITH addr AS (
  SELECT DISTINCT a.city, a.state_province_code, a.state_province_name, a.country_region_code, a.postal_code, a.state_province_id
  FROM (SELECT pa.address_id FROM stg.party_address pa JOIN stg.customer cu ON cu.person_id = pa.business_entity_id
        WHERE cu.store_id IS NULL AND pa.address_type = 'Home'
        UNION
        SELECT pa.address_id FROM stg.party_address pa JOIN stg.store s ON s.business_entity_id = pa.business_entity_id
        WHERE pa.address_type = 'Main Office') x
  JOIN stg.address a ON a.address_id = x.address_id)
SELECT CAST(ROW_NUMBER() OVER (ORDER BY a.country_region_code, a.state_province_code, a.city, a.postal_code) AS integer),
       a.city, a.state_province_code, a.state_province_name, a.country_region_code, c.name, l.spanish_name, l.french_name,
       a.postal_code, sp.territory_id
FROM addr a
LEFT JOIN stg.state_province sp ON sp.state_province_id = a.state_province_id
LEFT JOIN stg.country c ON c.country_region_code = a.country_region_code
LEFT JOIN dw_static.loc_country l ON l.country_region_code = a.country_region_code;

-- DimCustomer: individual (internet) customers; customer_key = CustomerID so static FactSurveyResponse keeps joining.
DELETE FROM dw.dim_customer;
INSERT INTO dw.dim_customer
WITH email AS (SELECT business_entity_id, email_address, ROW_NUMBER() OVER (PARTITION BY business_entity_id ORDER BY email_address_id) AS rn FROM stg.email_address),
phone AS (SELECT business_entity_id, phone_number, ROW_NUMBER() OVER (PARTITION BY business_entity_id ORDER BY phone_number_type_id, phone_number) AS rn FROM stg.phone),
home AS (SELECT pa.business_entity_id, a.address_line1, a.address_line2, a.city, a.state_province_code, a.postal_code, a.country_region_code,
                ROW_NUMBER() OVER (PARTITION BY pa.business_entity_id ORDER BY CASE WHEN pa.address_type = 'Home' THEN 0 ELSE 1 END, pa.address_id) AS rn
         FROM stg.party_address pa JOIN stg.address a ON a.address_id = pa.address_id)
SELECT cu.customer_id, g.geography_key, cu.account_number, p.title, p.first_name, p.middle_name, p.last_name, p.name_style,
       CAST(LEFT(p.demo_birth_date, 10) AS date), p.demo_marital_status, p.suffix, p.demo_gender, e.email_address,
       -- yearly income band '25001-50000' -> lower bound rounded like the DW (25001 -> 30000 etc. is not derivable; keep band floor)
       CAST(CASE WHEN p.demo_yearly_income LIKE 'greater%' THEN '150000'
                 WHEN p.demo_yearly_income LIKE '%-%' THEN SPLIT_PART(p.demo_yearly_income, '-', 1) END AS decimal(19,4)),
       CAST(p.demo_total_children AS smallint), CAST(p.demo_number_children_at_home AS smallint), p.demo_education, p.demo_occupation,
       p.demo_home_owner_flag, CAST(p.demo_number_cars_owned AS smallint), h.address_line1, h.address_line2, ph.phone_number,
       CAST(LEFT(p.demo_date_first_purchase, 10) AS date), p.demo_commute_distance
FROM stg.customer cu
JOIN stg.person p ON p.business_entity_id = cu.person_id
LEFT JOIN email e ON e.business_entity_id = cu.person_id AND e.rn = 1
LEFT JOIN phone ph ON ph.business_entity_id = cu.person_id AND ph.rn = 1
LEFT JOIN home h ON h.business_entity_id = cu.person_id AND h.rn = 1
LEFT JOIN dw.dim_geography g ON g.city = h.city AND g.state_province_code = h.state_province_code AND g.postal_code = h.postal_code
                            AND g.country_region_code = h.country_region_code
WHERE cu.store_id IS NULL;

-- DimReseller: stores; alternate key = the store customer's AccountNumber.
DELETE FROM dw.dim_reseller;
INSERT INTO dw.dim_reseller
WITH office AS (SELECT pa.business_entity_id, a.address_line1, a.address_line2, a.city, a.state_province_code, a.postal_code, a.country_region_code,
                       ROW_NUMBER() OVER (PARTITION BY pa.business_entity_id ORDER BY CASE WHEN pa.address_type = 'Main Office' THEN 0 ELSE 1 END, pa.address_id) AS rn
                FROM stg.party_address pa JOIN stg.address a ON a.address_id = pa.address_id),
acct AS (SELECT store_id, account_number, ROW_NUMBER() OVER (PARTITION BY store_id ORDER BY customer_id) AS rn FROM stg.customer WHERE store_id IS NOT NULL)
SELECT CAST(ROW_NUMBER() OVER (ORDER BY s.business_entity_id) AS integer), g.geography_key, ac.account_number,
       CASE s.demo_business_type WHEN 'BM' THEN 'Value Added Reseller' WHEN 'BS' THEN 'Specialty Bike Shop' WHEN 'OS' THEN 'Warehouse' ELSE s.demo_business_type END,
       s.name, CAST(s.demo_number_employees AS integer), s.demo_specialty, o.address_line1, o.address_line2,
       CAST(s.demo_annual_sales AS decimal(19,4)), s.demo_bank_name, CAST(s.demo_annual_revenue AS decimal(19,4)), CAST(s.demo_year_opened AS integer), s.business_entity_id
FROM stg.store s
LEFT JOIN acct ac ON ac.store_id = s.business_entity_id AND ac.rn = 1
LEFT JOIN office o ON o.business_entity_id = s.business_entity_id AND o.rn = 1
LEFT JOIN dw.dim_geography g ON g.city = o.city AND g.state_province_code = o.state_province_code AND g.postal_code = o.postal_code
                            AND g.country_region_code = o.country_region_code;

-- DimProduct: SCD2, one row per list-price history version (products without price history get one row).
-- product_key is deterministic: ordered by ProductID, version start date.
DELETE FROM dw.dim_product;
INSERT INTO dw.dim_product
WITH versions AS (
  SELECT p.product_id, h.start_date, h.end_date, h.list_price FROM stg.product p JOIN stg.list_price_history h ON h.product_id = p.product_id
  UNION ALL
  SELECT p.product_id, p.sell_start_date, CAST(NULL AS timestamp), p.list_price FROM stg.product p
  WHERE NOT EXISTS (SELECT 1 FROM stg.list_price_history h WHERE h.product_id = p.product_id)),
cost AS (SELECT product_id, start_date, standard_cost FROM stg.cost_history),
descr AS (SELECT product_model_id, MAX(CASE WHEN TRIM(culture_id) = 'en' THEN description END) AS en,
                 MAX(CASE WHEN TRIM(culture_id) = 'fr' THEN description END) AS fr
          FROM stg.model_description GROUP BY product_model_id)
SELECT CAST(ROW_NUMBER() OVER (ORDER BY v.product_id, v.start_date) AS integer), p.product_number, p.product_subcategory_id,
       p.weight_unit_measure_code, p.size_unit_measure_code, p.name, l.spanish_name, l.french_name,
       COALESCE(c.standard_cost, CASE WHEN v.end_date IS NULL THEN NULLIF(p.standard_cost, 0) END), p.finished_goods_flag, p.color,
       p.safety_stock_level, p.reorder_point, CASE WHEN p.finished_goods_flag THEN v.list_price END, p.size, p.weight,
       p.days_to_manufacture, p.product_line,
       CASE WHEN p.finished_goods_flag THEN CAST(v.list_price * 0.6 AS decimal(19,4)) END,  -- ufnGetProductDealerPrice: 60% of list
       p.class, p.style, p.model_name, d.en, d.fr, v.start_date, v.end_date, CASE WHEN v.end_date IS NULL THEN 'Current' END, p.product_id
FROM versions v
JOIN stg.product p ON p.product_id = v.product_id
LEFT JOIN cost c ON c.product_id = v.product_id AND c.start_date = v.start_date
LEFT JOIN descr d ON d.product_model_id = p.product_model_id
LEFT JOIN dw_static.loc_product_name l ON l.product_alternate_key = p.product_number;

-- DimEmployee: SCD2, one row per department assignment. Parent from the OrganizationNode path (org_path).
DELETE FROM dw.dim_employee;
INSERT INTO dw.dim_employee
WITH v AS (
  SELECT e.*, da.department_name, CAST(da.start_date AS date) AS v_start, CAST(da.end_date AS date) AS v_end,
         CAST(ROW_NUMBER() OVER (ORDER BY e.business_entity_id, da.start_date, da.department_id) AS integer) AS employee_key
  FROM stg.employee e JOIN stg.department_assignment da ON da.business_entity_id = e.business_entity_id),
cur AS (SELECT business_entity_id, org_path, national_id_number, employee_key,
               ROW_NUMBER() OVER (PARTITION BY business_entity_id ORDER BY CASE WHEN v_end IS NULL THEN 0 ELSE 1 END, v_start DESC) AS rn FROM v),
pay AS (SELECT business_entity_id, rate, pay_frequency, ROW_NUMBER() OVER (PARTITION BY business_entity_id ORDER BY rate_change_date DESC) AS rn FROM stg.pay_rate),
email AS (SELECT business_entity_id, email_address, ROW_NUMBER() OVER (PARTITION BY business_entity_id ORDER BY email_address_id) AS rn FROM stg.email_address),
phone AS (SELECT business_entity_id, phone_number, ROW_NUMBER() OVER (PARTITION BY business_entity_id ORDER BY phone_number_type_id) AS rn FROM stg.phone)
SELECT v.employee_key, par.employee_key, v.national_id_number, par.national_id_number, COALESCE(sp.territory_id, 11),
       v.first_name, v.last_name, p.middle_name, p.name_style, v.job_title, CAST(v.hire_date AS date), CAST(v.birth_date AS date),
       v.login_id, em.email_address, ph.phone_number, v.marital_status, v.salaried_flag, v.gender, pay.pay_frequency, pay.rate,
       v.vacation_hours, v.sick_leave_hours, v.current_flag, CASE WHEN sp.business_entity_id IS NULL THEN false ELSE true END,
       v.department_name, v.v_start, v.v_end, CASE WHEN v.v_end IS NULL THEN 'Current' END, v.business_entity_id
FROM v
LEFT JOIN cur par ON par.rn = 1 AND v.org_path <> '/' AND par.org_path = REGEXP_REPLACE(v.org_path, '[0-9]+/$', '')
LEFT JOIN stg.person p ON p.business_entity_id = v.business_entity_id
LEFT JOIN stg.sales_person sp ON sp.business_entity_id = v.business_entity_id
LEFT JOIN pay ON pay.business_entity_id = v.business_entity_id AND pay.rn = 1
LEFT JOIN email em ON em.business_entity_id = v.business_entity_id AND em.rn = 1
LEFT JOIN phone ph ON ph.business_entity_id = v.business_entity_id AND ph.rn = 1;
