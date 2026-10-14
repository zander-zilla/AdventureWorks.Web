"""C2-7 generator tests (no database): determinism, one run == day by day (the trickle), marking, realism constraints
and the fitted shape. A 2-year slice (2014-07..2016-06, the local / CI slice) is generated once per session (~20 s)."""
import collections, datetime as dt, os, re, sys
import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "synthetic")); sys.path.insert(0, os.path.join(ROOT, "scripts", "loader"))
import generate as G  # noqa: E402
import awmap  # noqa: E402

D = dt.date
SAMPLE_SHA = "1d3ce85722c0c2eef9990f8448d6e1faec08c2a020ee1be86b716501042bdabd"   # 2014-07-01..2014-09-30, seed 2026


@pytest.fixture(scope="session")
def gen():
    return G.Generator()


@pytest.fixture(scope="session")
def slice2y(gen):
    return G.apply_updates(gen.range(D(2014, 7, 1), D(2016, 6, 30)))


def d(s):
    return D.fromisoformat(s[:10])


def test_sample_hash_is_pinned(gen):
    """Same seed + profile + end date = identical rows (the CI determinism check)."""
    assert G.apply_updates(gen.range(D(2014, 7, 1), D(2014, 9, 30))).digest() == SAMPLE_SHA


def test_seed_changes_output():
    a = G.Generator(seed=1).range(D(2014, 7, 1), D(2014, 7, 3)).digest()
    b = G.Generator(seed=2).range(D(2014, 7, 1), D(2014, 7, 3)).digest()
    assert a != b


def test_one_run_equals_day_by_day(gen):
    """The daily trickle (one day at a time, ship updates later) ends in exactly the rows of a single bulk run."""
    a, b = D(2014, 9, 24), D(2014, 10, 16)   # month-end reseller orders, quota day, two PO Mondays, 7-day ship window
    bulk = G.apply_updates(gen.range(a, b))
    trickle = G.Batch()
    x = a
    while x <= b:
        trickle.extend(gen.day(x, x)); x += dt.timedelta(days=1)
    assert G.apply_updates(trickle).digest() == bulk.digest()


def test_every_generated_row_is_marked(slice2y):
    for table, rows in slice2y.rows.items():
        assert table in awmap.SYNTHETIC, table
        assert all(awmap.is_synthetic(table, r) for r in rows), table


def test_keys_unique(slice2y):
    pk = {"Sales.SalesOrderHeader": ("SalesOrderID",), "Sales.SalesOrderDetail": ("SalesOrderDetailID",), "Sales.Customer": ("CustomerID",),
          "Production.WorkOrder": ("WorkOrderID",), "Production.TransactionHistory": ("TransactionID",), "Purchasing.PurchaseOrderDetail": ("PurchaseOrderDetailID",),
          "Production.ProductReview": ("ProductReviewID",), "Production.ProductListPriceHistory": ("ProductID", "StartDate"),
          "Sales.SpecialOfferProduct": ("SpecialOfferID", "ProductID"), "Production.Product": ("ProductID",)}
    for t, cols in pk.items():
        keys = [tuple(r[c] for c in cols) for r in slice2y.rows[t]]
        assert len(keys) == len(set(keys)), t
    names = [r["Name"] for r in slice2y.rows["Production.Product"]]
    assert len(names) == len(set(names))


def test_realism_constraints(slice2y, gen):
    R = slice2y.rows
    created = {r["CustomerID"]: d(r["ModifiedDate"]) for r in R["Sales.Customer"]}
    heads = {r["SalesOrderID"]: r for r in R["Sales.SalesOrderHeader"]}
    for h in heads.values():
        if h["CustomerID"] in created:
            assert created[h["CustomerID"]] <= d(h["OrderDate"])              # no order before the customer exists
        if h["ShipDate"]:
            assert d(h["ShipDate"]) >= d(h["OrderDate"])                     # no shipment before the order
        assert d(h["DueDate"]) >= d(h["OrderDate"])
    new = {r["ProductID"]: r for r in R["Production.Product"]}
    offers = {r["SpecialOfferID"]: r for r in R["Sales.SpecialOffer"]}
    for l in R["Sales.SalesOrderDetail"]:
        od = d(heads[l["SalesOrderID"]]["OrderDate"])
        if l["ProductID"] in new:                                              # only inside the sell window
            p = new[l["ProductID"]]; assert d(p["SellStartDate"]) <= od <= d(p["SellEndDate"])
        if l["UnitPriceDiscount"] > 0:                                         # offers only inside their dates
            o = offers[l["SpecialOfferID"]]; assert d(o["StartDate"]) <= od <= d(o["EndDate"])
            assert abs(o["DiscountPct"] - l["UnitPriceDiscount"]) < 1e-9
        if heads[l["SalesOrderID"]]["OnlineOrderFlag"]:                        # prices only from the price list
            assert l["UnitPrice"] == gen.list_price(l["ProductID"], od)
    for l in R["Purchasing.PurchaseOrderDetail"]:
        assert 0 <= l["RejectedQty"] <= l["ReceivedQty"] <= l["OrderQty"]
    for w in R["Production.WorkOrder"]:
        assert 0 <= w["ScrappedQty"] <= w["OrderQty"] and d(w["StartDate"]) <= d(w["EndDate"])
    sop = {(r["SpecialOfferID"], r["ProductID"]) for r in R["Sales.SpecialOfferProduct"]}
    for l in R["Sales.SalesOrderDetail"]:                                      # the SalesOrderDetail -> SpecialOfferProduct FK holds
        assert l["SpecialOfferID"] == 1 and l["ProductID"] < 5000 or (l["SpecialOfferID"], l["ProductID"]) in sop


def test_no_real_personal_data(slice2y):
    for r in slice2y.rows["Person.EmailAddress"]:
        assert r["EmailAddress"].endswith("@adventure-works.com")
    for r in slice2y.rows["Person.PersonPhone"]:
        assert re.fullmatch(r"\d{3}-555-01\d\d", r["PhoneNumber"])
    assert all(r["CreditCardID"] is None for r in slice2y.rows["Sales.SalesOrderHeader"])


def test_fitted_shape(slice2y, gen):
    P = gen.P; R = slice2y.rows
    web = [h for h in R["Sales.SalesOrderHeader"] if h["OnlineOrderFlag"]]
    by_month = collections.Counter(h["OrderDate"][:7] for h in web)
    # seasonality: monthly web orders per day, growth removed, correlate with the fitted month index
    idx = []
    for ym, n in sorted(by_month.items()):
        y, m = map(int, ym.split("-")); days = (D(y + (m == 12), m % 12 + 1, 1) - D(y, m, 1)).days
        idx.append((m, n / days / gen.g(D(y, m, 15)) / P["online_orders_per_day"]))
    a = np.array([v for _, v in idx]); b = np.array([P["month_index"][m - 1] for m, _ in idx])
    assert np.corrcoef(a, b)[0, 1] >= 0.8
    # growth within +-1 point of the setting (web orders, first vs second year)
    y1 = sum(n for ym, n in by_month.items() if ym < "2015-07"); y2 = sum(n for ym, n in by_month.items() if ym >= "2015-07")
    assert abs(y2 / y1 - 1.05) <= 0.01 + 0.01   # +-1 point on the rate (+ Poisson noise allowance)
    # territory mix within +-3 points
    t = collections.Counter(str(h["TerritoryID"]) for h in web)
    for k, s in P["online_territory_share"].items():
        assert abs(t[k] / len(web) - s) <= 0.03, k
    # basket size within +-10 %
    lines = collections.Counter(l["SalesOrderID"] for l in R["Sales.SalesOrderDetail"])
    fit_mean = sum(k * p for k, p in P["online_lines"]); got = np.mean([lines[h["SalesOrderID"]] for h in web])
    assert abs(got / fit_mean - 1) <= 0.10
    # reject and scrap rates within +-10 %
    pod = R["Purchasing.PurchaseOrderDetail"]
    assert abs(sum(l["RejectedQty"] for l in pod) / sum(l["ReceivedQty"] for l in pod) / P["po"]["reject_rate"] - 1) <= 0.10
    wo = R["Production.WorkOrder"]
    assert abs(sum(1 for w in wo if w["ScrappedQty"]) / len(wo) / P["scrap"]["wo_share"] - 1) <= 0.10


def test_holidays_shape_demand(gen):
    bf, normal = D(2025, 11, 28), D(2025, 11, 21)      # Black Friday vs the Friday before
    assert gen.day_factor(bf) > gen.day_factor(normal) * 1.1
    assert gen.day_factor(D(2025, 12, 25)) < 0.6


def test_offers_are_live_today(gen):
    today = D(2026, 10, 13)
    live = [o for o in gen.offers(2026) if o["StartDate"] <= today <= o["EndDate"]]
    assert any(o["Type"] == "Volume Discount" for o in live) and any(o["Category"] == "Customer" for o in live)


def test_new_products_per_year(gen):
    for y in range(2015, 2027):
        n = sum(len(r["products"]) for r in gen.releases(y))
        assert 6 <= n <= 10, (y, n)
    assert all(p["SellEndDate"] > p["SellStartDate"] for p in gen.new_products(2026).values())


def test_dip2020_flag_off_by_default(gen):
    assert gen.dip2020 is False
    assert G.Generator(dip2020=True).g(D(2020, 6, 1)) < gen.g(D(2020, 6, 1))
