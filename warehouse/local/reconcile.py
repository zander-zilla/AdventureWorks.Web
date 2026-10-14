#!/usr/bin/env python3
"""Reconcile the rebuilt star schema (Postgres stand-in, schema dw) against the original AdventureWorksDW2022 (schema ref,
copied by static_export.py --pg). Writes a JSON report; exits 1 when a gated check fails.
Facts are matched on (SalesOrderNumber, SalesOrderLineNumber) because AdventureWorksDW2022 ships shifted dates."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import pg

SCHEMA = {"dw": "dw"}
# C2-7 --original-only: the rebuilt star restricted to the ORIGINAL rows (generated rows sit in fixed key ranges, see
# scripts/loader/awmap.py SYNTHETIC), so the Chapter 1 reconcile against AdventureWorksDW2022 stays exact with generated data loaded.
ORIGINAL_FILTERS = {
    "fact_internet_sales": "CAST(SUBSTRING(sales_order_number FROM 3) AS integer) < 1000000",
    "fact_reseller_sales": "CAST(SUBSTRING(sales_order_number FROM 3) AS integer) < 1000000",
    "fact_internet_sales_reason": "CAST(SUBSTRING(sales_order_number FROM 3) AS integer) < 1000000",
    "dim_customer": "CAST(SUBSTRING(customer_alternate_key FROM 3) AS integer) < 500000",
    "dim_product": "product_alternate_key NOT LIKE 'SY-%' AND (start_date IS NULL OR start_date < DATE '2014-07-01')",
    "dim_promotion": "promotion_alternate_key < 100",
    "dim_date": "date_key <= 20141231",
    "fact_sales_quota": "date < DATE '2014-07-01'",
}
ORIGINAL_KNOWN = {"fact_product_inventory": "C2-7: inventory balances are cumulative, generated movements change every later balance; "
                  "the original-only check of this fact is the Chapter 1 run without generated data"}


def original_views(cur):
    cur.execute("CREATE SCHEMA IF NOT EXISTS dwo")
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'dw'")
    for (t,) in cur.fetchall():
        cur.execute("CREATE OR REPLACE VIEW dwo.%s AS SELECT * FROM dw.%s%s" % (t, t, (" WHERE " + ORIGINAL_FILTERS[t]) if t in ORIGINAL_FILTERS else ""))
    cur.connection.commit()
    SCHEMA["dw"] = "dwo"


def q(cur, sql):
    if SCHEMA["dw"] != "dw":
        sql = sql.replace("dw.", SCHEMA["dw"] + ".")
    cur.execute(sql); r = cur.fetchone(); return [float(x) if x is not None and not isinstance(x, (int, str)) else x for x in r]

COUNT_TABLES = ["dim_date", "dim_customer", "dim_geography", "dim_reseller", "dim_product", "dim_product_category", "dim_product_subcategory",
                "dim_promotion", "dim_sales_territory", "dim_employee", "dim_currency", "dim_sales_reason", "fact_internet_sales",
                "fact_reseller_sales", "fact_internet_sales_reason", "fact_sales_quota", "fact_currency_rate"]
# differences explained in docs/design/warehouse.md (Reconciliation); everything else must match exactly
KNOWN = {"dim_geography": "DW has 655 rows incl. geographies of addresses no customer/reseller points at today; rebuilt = distinct home/main-office addresses",
         "fact_reseller_sales": "OLTP has 64 more offline lines than the DW snapshot (orders added after the DW was built)",
         "fact_currency_rate": "DW contains 732 synthesised rate days that are not in Sales.CurrencyRate",
         "dim_date": "fiscal-year naming: DW uses FY = start year + 1 before 2011 and FY = start year from 2011 on (date-shift artefact); rebuilt uses the 2011+ rule throughout",
         "dim_customer.birth_date/yearly_income/date_first_purchase": "DW values are synthetic/shifted; rebuilt takes them from Person.Demographics (yearly income = band floor)",
         "fact_reseller_sales.tax_amt/freight": "DW uses flat 8% tax / 2.5% freight of SalesAmount; rebuilt allocates the real order-header TaxAmt/Freight by line share",
         "dim_currency keys": "DW currency keys are not in code order; rebuilt keys are by code. Facts match on the currency code",
         "fact_product_inventory": "DW synthesises 606 product versions x 1,281 days; rebuilt = per product from first movement to last movement date"}

MEASURES = "SUM(%s.order_quantity), SUM(%s.sales_amount), SUM(%s.tax_amt), SUM(%s.freight), SUM(%s.total_product_cost), SUM(%s.extended_amount)"

def fact(cur, t):
    m = lambda a: MEASURES % ((a,) * 6)
    ours = q(cur, "SELECT COUNT(*), %s FROM dw.%s f" % (m("f"), t))
    ref = q(cur, "SELECT COUNT(*), %s FROM ref.%s r" % (m("r"), t))
    on = "f.sales_order_number = r.sales_order_number AND f.sales_order_line_number = r.sales_order_line_number"
    matched = q(cur, "SELECT COUNT(*), %s, %s FROM dw.%s f JOIN ref.%s r ON %s" % (m("f"), m("r"), t, t, on))
    prod = q(cur, """SELECT COUNT(*) FROM dw.%s f JOIN ref.%s r ON %s JOIN dw.dim_product dp ON dp.product_key = f.product_key
                     JOIN ref.dim_product rp ON rp.product_key = r.product_key
                     WHERE dp.product_alternate_key = rp.product_alternate_key AND dp.list_price = rp.list_price""" % (t, t, on))[0]
    cost = q(cur, "SELECT COUNT(*) FROM dw.%s f JOIN ref.%s r ON %s WHERE f.product_standard_cost = r.product_standard_cost" % (t, t, on))[0]
    names = ["order_quantity", "sales_amount", "tax_amt", "freight", "total_product_cost", "extended_amount"]
    out = {"rows": ours[0], "ref_rows": ref[0], "matched_lines": matched[0], "only_in_rebuilt": ours[0] - matched[0], "only_in_dw": ref[0] - matched[0],
           "product_version_match": prod, "standard_cost_match": cost,
           "measures_matched_lines": {n: {"rebuilt": round(matched[1 + i], 4), "dw": round(matched[7 + i], 4),
                                          "diff_pct": round(100 * (matched[1 + i] - matched[7 + i]) / matched[7 + i], 6) if matched[7 + i] else 0}
                                      for i, n in enumerate(names)},
           "measures_all": {n: {"rebuilt": round(ours[1 + i], 4), "dw": round(ref[1 + i], 4)} for i, n in enumerate(names)}}
    if t == "fact_internet_sales":
        out["customer_match"] = q(cur, "SELECT COUNT(*) FROM dw.%s f JOIN ref.%s r ON %s WHERE f.customer_key = r.customer_key" % (t, t, on))[0]
    else:
        out["reseller_match"] = q(cur, """SELECT COUNT(*) FROM dw.%s f JOIN ref.%s r ON %s JOIN dw.dim_reseller a ON a.reseller_key = f.reseller_key
                                         JOIN ref.dim_reseller b ON b.reseller_key = r.reseller_key WHERE a.reseller_alternate_key = b.reseller_alternate_key""" % (t, t, on))[0]
        out["employee_match"] = q(cur, """SELECT COUNT(*) FROM dw.%s f JOIN ref.%s r ON %s JOIN dw.dim_employee a ON a.employee_key = f.employee_key
                                         JOIN ref.dim_employee b ON b.employee_key = r.employee_key
                                         WHERE a.employee_national_id_alternate_key = b.employee_national_id_alternate_key""" % (t, t, on))[0]
    out["territory_match"] = q(cur, "SELECT COUNT(*) FROM dw.%s f JOIN ref.%s r ON %s WHERE f.sales_territory_key = r.sales_territory_key" % (t, t, on))[0]
    out["promotion_match"] = q(cur, "SELECT COUNT(*) FROM dw.%s f JOIN ref.%s r ON %s WHERE f.promotion_key = r.promotion_key" % (t, t, on))[0]
    out["currency_match"] = q(cur, """SELECT COUNT(*) FROM dw.%s f JOIN ref.%s r ON %s JOIN dw.dim_currency a ON a.currency_key = f.currency_key
                                     JOIN ref.dim_currency b ON b.currency_key = r.currency_key WHERE a.currency_alternate_key = b.currency_alternate_key""" % (t, t, on))[0]
    return out

def dims(cur):
    d = {}
    d["dim_date"] = {"attribute_mismatches": q(cur, """SELECT COUNT(*) FROM dw.dim_date a JOIN ref.dim_date b ON a.date_key = b.date_key WHERE
        (a.day_number_of_week <> b.day_number_of_week OR a.english_day_name_of_week <> b.english_day_name_of_week OR a.week_number_of_year <> b.week_number_of_year
        OR a.english_month_name <> b.english_month_name OR a.spanish_month_name <> b.spanish_month_name OR a.french_day_name_of_week <> b.french_day_name_of_week
        OR a.calendar_quarter <> b.calendar_quarter OR a.calendar_semester <> b.calendar_semester OR a.fiscal_quarter <> b.fiscal_quarter
        OR a.fiscal_year <> b.fiscal_year OR a.fiscal_semester <> b.fiscal_semester OR a.day_number_of_year <> b.day_number_of_year)
        AND a.date_key >= 20110101""")[0],
        "fiscal_year_mismatches_before_2011": q(cur, "SELECT COUNT(*) FROM dw.dim_date a JOIN ref.dim_date b ON a.date_key = b.date_key WHERE a.fiscal_year <> b.fiscal_year AND a.date_key < 20110101")[0]}
    d["dim_customer"] = dict(zip(["key_and_alt_key_match", "name_match", "email_match", "birth_date_match", "education_match", "geography_match"], q(cur, """
        SELECT COUNT(*), SUM(CASE WHEN a.first_name = b.first_name AND a.last_name = b.last_name THEN 1 ELSE 0 END),
               SUM(CASE WHEN a.email_address = b.email_address THEN 1 ELSE 0 END), SUM(CASE WHEN a.birth_date = b.birth_date THEN 1 ELSE 0 END),
               SUM(CASE WHEN a.english_education = b.english_education THEN 1 ELSE 0 END),
               SUM(CASE WHEN ga.city = gb.city AND ga.postal_code = gb.postal_code THEN 1 ELSE 0 END)
        FROM dw.dim_customer a JOIN ref.dim_customer b ON a.customer_key = b.customer_key AND a.customer_alternate_key = b.customer_alternate_key
        LEFT JOIN dw.dim_geography ga ON ga.geography_key = a.geography_key LEFT JOIN ref.dim_geography gb ON gb.geography_key = b.geography_key""")))
    d["dim_reseller"] = dict(zip(["alt_key_match", "name_match", "business_type_match", "annual_sales_match"], q(cur, """
        SELECT COUNT(*), SUM(CASE WHEN a.reseller_name = b.reseller_name THEN 1 ELSE 0 END), SUM(CASE WHEN a.business_type = b.business_type THEN 1 ELSE 0 END),
               SUM(CASE WHEN a.annual_sales = b.annual_sales THEN 1 ELSE 0 END)
        FROM dw.dim_reseller a JOIN ref.dim_reseller b ON a.reseller_alternate_key = b.reseller_alternate_key""")))
    d["dim_product"] = dict(zip(["alt_key_start_match", "list_price_match", "standard_cost_match", "dealer_price_match", "status_match"], q(cur, """
        SELECT COUNT(*), SUM(CASE WHEN COALESCE(a.list_price, -1) = COALESCE(b.list_price, -1) THEN 1 ELSE 0 END),
               SUM(CASE WHEN COALESCE(a.standard_cost, -1) = COALESCE(b.standard_cost, -1) THEN 1 ELSE 0 END),
               SUM(CASE WHEN COALESCE(a.dealer_price, -1) = COALESCE(b.dealer_price, -1) THEN 1 ELSE 0 END),
               SUM(CASE WHEN COALESCE(a.status, '') = COALESCE(b.status, '') THEN 1 ELSE 0 END)
        FROM (SELECT p.*, ROW_NUMBER() OVER (PARTITION BY product_alternate_key ORDER BY start_date) AS v FROM dw.dim_product p) a
        JOIN (SELECT p.*, ROW_NUMBER() OVER (PARTITION BY product_alternate_key ORDER BY start_date) AS v FROM ref.dim_product p) b
          ON a.product_alternate_key = b.product_alternate_key AND a.v = b.v""")))
    d["dim_employee"] = dict(zip(["national_id_version_match", "department_match", "parent_match", "territory_match"], q(cur, """
        SELECT COUNT(*), SUM(CASE WHEN a.department_name = b.department_name THEN 1 ELSE 0 END),
               SUM(CASE WHEN COALESCE(pa.employee_national_id_alternate_key, '') = COALESCE(pb.employee_national_id_alternate_key, '') THEN 1 ELSE 0 END),
               SUM(CASE WHEN a.sales_territory_key = b.sales_territory_key THEN 1 ELSE 0 END)
        FROM (SELECT e.*, ROW_NUMBER() OVER (PARTITION BY employee_national_id_alternate_key ORDER BY start_date) AS v FROM dw.dim_employee e) a
        JOIN (SELECT e.*, ROW_NUMBER() OVER (PARTITION BY employee_national_id_alternate_key ORDER BY start_date) AS v FROM ref.dim_employee e) b
          ON a.employee_national_id_alternate_key = b.employee_national_id_alternate_key AND a.v = b.v
        LEFT JOIN dw.dim_employee pa ON pa.employee_key = a.parent_employee_key LEFT JOIN ref.dim_employee pb ON pb.employee_key = b.parent_employee_key""")))
    d["dim_geography"] = {"city_state_postal_match": q(cur, """SELECT COUNT(*) FROM dw.dim_geography a JOIN ref.dim_geography b
        ON a.city = b.city AND a.state_province_code = b.state_province_code AND a.postal_code = b.postal_code""")[0]}
    for t, k, n in [("dim_currency", "currency_alternate_key", "currency_name"), ("dim_promotion", "promotion_key", "english_promotion_name"),
                    ("dim_sales_territory", "sales_territory_key", "sales_territory_region"), ("dim_sales_reason", "sales_reason_key", "sales_reason_name"),
                    ("dim_product_category", "product_category_key", "english_product_category_name"),
                    ("dim_product_subcategory", "product_subcategory_key", "english_product_subcategory_name")]:
        d[t] = {"key_and_name_match": q(cur, "SELECT COUNT(*) FROM dw.%s a JOIN ref.%s b ON a.%s = b.%s AND a.%s = b.%s" % (t, t, k, k, n, n))[0]}
    d["dim_currency"]["key_match"] = q(cur, "SELECT COUNT(*) FROM dw.dim_currency a JOIN ref.dim_currency b ON a.currency_key = b.currency_key AND a.currency_alternate_key = b.currency_alternate_key")[0]
    return d

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/tmp/warehouse-reconcile.json")
    ap.add_argument("--original-only", action="store_true", help="C2-7: reconcile only the original rows (generated data loaded)"); a = ap.parse_args()
    cur = pg.connect().cursor(); rep = {"counts": {}, "known_differences": KNOWN}
    if a.original_only:
        original_views(cur); KNOWN.update(ORIGINAL_KNOWN); rep["original_only"] = True
    for t in COUNT_TABLES:
        rep["counts"][t] = {"rebuilt": q(cur, "SELECT COUNT(*) FROM dw.%s" % t)[0], "dw": q(cur, "SELECT COUNT(*) FROM ref.%s" % t)[0]}
    rep["counts"]["fact_product_inventory"] = {"rebuilt": q(cur, "SELECT COUNT(*) FROM dw.fact_product_inventory")[0], "dw": 776286}
    rep["dims"] = dims(cur)
    rep["facts"] = {t: fact(cur, t) for t in ("fact_internet_sales", "fact_reseller_sales")}
    rep["facts"]["fact_internet_sales_reason"] = {"matched": q(cur, """SELECT COUNT(*) FROM dw.fact_internet_sales_reason a JOIN ref.fact_internet_sales_reason b
        ON a.sales_order_number = b.sales_order_number AND a.sales_order_line_number = b.sales_order_line_number AND a.sales_reason_key = b.sales_reason_key""")[0]}
    rep["facts"]["fact_sales_quota"] = dict(zip(["rebuilt_sum", "dw_sum"], q(cur, "SELECT (SELECT SUM(sales_amount_quota) FROM dw.fact_sales_quota), (SELECT SUM(sales_amount_quota) FROM ref.fact_sales_quota)")))
    rep["facts"]["fact_currency_rate"] = dict(zip(["rebuilt_currencies", "dw_currencies"], q(cur, "SELECT (SELECT COUNT(DISTINCT currency_key) FROM dw.fact_currency_rate), (SELECT COUNT(DISTINCT currency_key) FROM ref.fact_currency_rate)")))
    rep["facts"]["fact_product_inventory"] = dict(zip(["products", "negative_balances", "final_balance_vs_on_hand_mismatches"], q(cur, """
        SELECT (SELECT COUNT(DISTINCT product_key) FROM dw.fact_product_inventory), (SELECT COUNT(*) FROM dw.fact_product_inventory WHERE units_balance < 0),
               (SELECT COUNT(*) FROM (SELECT dp.product_id, f.units_balance, ROW_NUMBER() OVER (PARTITION BY dp.product_id ORDER BY f.date_key DESC) rn
                                      FROM dw.fact_product_inventory f JOIN dw.dim_product dp ON dp.product_key = f.product_key) x
                LEFT JOIN (SELECT product_id, SUM(quantity) q FROM stg.product_inventory GROUP BY product_id) o ON o.product_id = x.product_id
                WHERE x.rn = 1 AND x.units_balance <> COALESCE(o.q, 0))""")))
    fails = gate(rep); rep["gate_failures"] = fails
    json.dump(rep, open(a.out, "w"), indent=1, default=str)
    print(json.dumps({"counts": rep["counts"], "gate_failures": fails}, indent=1))
    sys.exit(1 if fails else 0)

def gate(r):
    f = []
    for t, c in r["counts"].items():
        if t not in KNOWN and c["rebuilt"] != c["dw"]:
            f.append("%s rows %s != DW %s" % (t, c["rebuilt"], c["dw"]))
    if r["dims"]["dim_date"]["attribute_mismatches"]:
        f.append("dim_date attribute mismatches")
    for t in ("fact_internet_sales", "fact_reseller_sales"):
        x = r["facts"][t]
        if x["only_in_dw"]:
            f.append("%s: %d DW lines not rebuilt" % (t, x["only_in_dw"]))
        for n in ("order_quantity", "sales_amount", "extended_amount"):
            if abs(x["measures_matched_lines"][n]["diff_pct"]) > 0.0001:
                f.append("%s.%s differs %s%%" % (t, n, x["measures_matched_lines"][n]["diff_pct"]))
        for n in ("tax_amt", "freight"):  # allocated per line: rounding only (reseller: known difference, see KNOWN)
            if t == "fact_internet_sales" and abs(x["measures_matched_lines"][n]["diff_pct"]) > 0.01:
                f.append("%s.%s differs %s%%" % (t, n, x["measures_matched_lines"][n]["diff_pct"]))
    for k in ("product_version_match", "standard_cost_match", "territory_match", "promotion_match", "currency_match"):
        for t in ("fact_internet_sales", "fact_reseller_sales"):
            if r["facts"][t][k] != r["facts"][t]["matched_lines"]:
                f.append("%s.%s %s/%s" % (t, k, r["facts"][t][k], r["facts"][t]["matched_lines"]))
    for t, k in (("fact_internet_sales", "customer_match"), ("fact_reseller_sales", "reseller_match"), ("fact_reseller_sales", "employee_match")):
        if r["facts"][t][k] != r["facts"][t]["matched_lines"]:
            f.append("%s.%s %s/%s" % (t, k, r["facts"][t][k], r["facts"][t]["matched_lines"]))
    if r["facts"]["fact_internet_sales_reason"]["matched"] != r["counts"]["fact_internet_sales_reason"]["dw"]:
        f.append("fact_internet_sales_reason not fully matched")
    if r["facts"]["fact_product_inventory"]["final_balance_vs_on_hand_mismatches"] and not r.get("original_only"):
        f.append("fact_product_inventory final balance != on-hand")
    return f

if __name__ == "__main__":
    main()
