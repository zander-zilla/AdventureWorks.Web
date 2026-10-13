#!/usr/bin/env python3
"""C2-7 synthetic data generator: continues AdventureWorks from 2014-07-01 to an end date, seeded and repeatable.

Day-keyed and stateless: every random draw comes from a stream keyed by (seed, stream, day/entity), and every generated
key comes from a fixed slot of that day (awmap.SYNTHETIC ranges). Generating 2014-07-01..E in one run or one day at a time
(the daily trickle) gives the same rows. Rows that complete later (orders ship 7 days after the order) are written in their
final state when the end date already covers it, otherwise as "in process" plus an UPDATE emitted on the ship day.

Usage: python scripts/synthetic/generate.py --start 2014-07-01 --end 2014-09-30 [--seed 2026] [--hash]
Library: Generator(profile).day(date, end) -> Batch(rows={table: [row dicts]}, updates=[(table, set, where)])."""
import argparse, bisect, collections, datetime as dt, functools, hashlib, json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "profile.json")
ORIGIN = dt.date(2014, 7, 1)          # first generated day (original orders end 2014-06-30)
WO_FROM = dt.date(2014, 8, 1)         # original work orders run into July 2014
PO_FROM = dt.date(2014, 10, 6)        # original purchase orders run to 2014-09-22 (first Monday after)
GROWTH_CENTRE = dt.date(2013, 12, 15) # centre of the fit window
COLOURS = ["Teal", "Orange", "Graphite", "Sand", "Olive", "Navy", "Burgundy", "Lime", "Copper", "Ice"]
PRICE_RISE = {1: 0.03, 2: 0.02, 3: 0.01, 4: 0.0}   # yearly list-price change on 1 July, by category (bikes .. accessories)
TAX, FREIGHT = 0.08, 0.025                          # the AdventureWorks header rules (TaxAmt / Freight of SubTotal)
SHIP_DAYS, DUE_DAYS = 7, 12
STREAMS = {k: i for i, k in enumerate(["cust", "online", "reseller", "wo", "po", "review", "release", "retire", "quota", "returning", "mix"])}
REVIEW_TEXT = {1: "Disappointed - it did not last a season.", 2: "Not great value; the fit was off for me.", 3: "Does the job, nothing special.",
               4: "Solid and well made, would buy again.", 5: "Excellent - exactly what I needed for my rides."}
# slots per day / week (key = floor + index * slot + i), see awmap.SYNTHETIC
SLOT = {"cust": 100, "order": 500, "online_max": 300, "line": 9000, "wo": 110, "txn": 7000, "review": 5, "po": 100, "pod": 300}


def d2s(d):
    return d.isoformat() + "T00:00:00"


def money(x):
    return round(float(x) + 1e-9, 4)


def guid(table, key):
    """Deterministic rowguid with the fixed synthetic prefix 5157xxxx (marks generated rows in any copy of the data)."""
    h = hashlib.sha1(("%s:%s" % (table, key)).encode()).hexdigest()
    return "5157%s-%s-%s-%s-%s" % (h[:4], h[4:8], h[8:12], h[12:16], h[16:28])


class Batch:
    def __init__(self):
        self.rows = collections.defaultdict(list); self.updates = []

    def add(self, table, row):
        self.rows[table].append(row)

    def extend(self, other):
        for t, rs in other.rows.items():
            self.rows[t].extend(rs)
        self.updates.extend(other.updates)

    def counts(self):
        return {t: len(r) for t, r in sorted(self.rows.items())}

    def digest(self):
        h = hashlib.sha256()
        for t in sorted(self.rows):
            for r in self.rows[t]:
                h.update(json.dumps([t, r], sort_keys=True, default=str).encode())
        for u in self.updates:
            h.update(json.dumps(u, sort_keys=True, default=str).encode())
        return h.hexdigest()


class Generator:
    def __init__(self, profile=None, seed=2026, growth=0.05, dip2020=False):
        self.P = profile or json.load(open(PROFILE))
        self.seed, self.growth, self.dip2020 = seed, growth, dip2020
        P = self.P
        self.products = {p["ProductID"]: p for p in P["products"]}
        self.cat = {pid: p["cat"] for pid, p in self.products.items()}
        self.territories = sorted(P["online_territory_share"], key=int)
        self.tshare = np.array([P["online_territory_share"][t] for t in self.territories]); self.tshare /= self.tshare.sum()
        dist = lambda xs: (np.array([x[0] for x in xs]), np.array([x[1] for x in xs], float) / sum(x[1] for x in xs))
        self.lines_on, self.lines_res, self.qty_res = dist(P["online_lines"]), dist(P["reseller_lines"]), dist(P["reseller_qty"])
        self.ratings = dist(P["review_ratings"])
        self.scrap_ids, self.scrap_p = dist(P["scrap"]["reasons"])
        self.stores = P["stores"]
        self.store_w = np.array([s[5] for s in self.stores], float); self.store_w /= self.store_w.sum()
        self.models = sorted({p["ProductModelID"] for p in P["products"] if p["cat"] == 1 and (p["w_online"] or p["w_reseller"]) and p["ProductModelID"]})
        self.vendor_lines = P["vendor_products"]
        try:
            import holidays as _h
            self._holidays = _h
        except ImportError:  # the shape tests need it; generation without it would differ, so fail loudly
            raise SystemExit("pip install holidays (C2-7 decision 1: real calendar holidays)")
        self._cum_new = None

    # ---------------------------------------------------------------- random streams
    def rng(self, stream, *key):
        return np.random.Generator(np.random.PCG64(np.random.SeedSequence([self.seed, STREAMS[stream], *[int(k) for k in key]])))

    @staticmethod
    def idx(d):
        return (d - ORIGIN).days

    # ---------------------------------------------------------------- demand shape
    def g(self, d):
        f = (1 + self.growth) ** ((d - GROWTH_CENTRE).days / 365.25)
        if self.dip2020 and d.year == 2020 and d.month >= 3:
            f *= 0.85
        return f

    @functools.lru_cache(maxsize=64)
    def _hol(self, cc, year):
        return self._holidays.country_holidays(cc, years=year)

    def hol_factor(self, cc, d):
        h = self._hol(cc, d.year)
        if cc == "US":
            tg = next((k for k, v in h.items() if "Thanksgiving" in v), None)
            if tg and d == tg + dt.timedelta(days=1):
                return 1.8   # Black Friday
            if tg and d == tg + dt.timedelta(days=4):
                return 1.5   # Cyber Monday
        if d.month == 12 and d.day == 25:
            return 0.4
        return 0.8 if d in h else 1.0

    def day_factor(self, d):
        return float(sum(s * self.hol_factor(self.P["territory_country"][t], d) for t, s in zip(self.territories, self.tshare)))

    def online_rate(self, d):
        P = self.P
        return P["online_orders_per_day"] * self.g(d) * P["month_index"][d.month - 1] * P["dow_index"][d.weekday()] * self.day_factor(d)

    def new_rate(self, d):
        return self.online_rate(d) * self.P["online_new_customer_share"]

    # ---------------------------------------------------------------- catalog over time
    @functools.lru_cache(maxsize=None)
    def retire_date(self, model_id):
        """Original bike models leave generated demand on a schedule (rows are never changed: Chapter 1 stays exact)."""
        y = int(self.rng("retire", model_id).integers(2017, 2031))
        return dt.date(y, 6, 30)

    @functools.lru_cache(maxsize=None)
    def releases(self, year):
        """New bike lines: 2 releases a year (1 Mar, 1 Sep), each a cloned original model in a new colour, all sizes (<= 5)."""
        out = []
        for k, rel in enumerate([dt.date(year, 3, 1), dt.date(year, 9, 1)]):
            if rel < ORIGIN:
                continue
            r = self.rng("release", year, k)
            live = [m for m in self.models if self.retire_date(m) > rel]
            model = live[int(r.integers(len(live)))]
            used = {p["Color"] for p in self.P["products"] if p["ProductModelID"] == model}
            colour = [c for c in COLOURS if c not in used][int(r.integers(len([c for c in COLOURS if c not in used])))]
            src = sorted([p for p in self.P["products"] if p["ProductModelID"] == model and p["FinishedGoodsFlag"]], key=lambda p: p["ProductID"])[:5]
            prods = []
            for i, s in enumerate(src):
                pid = 5000 + (year - 2014) * 20 + k * 10 + i
                prods.append({**s, "ProductID": pid, "src": s["ProductID"], "Color": colour,
                              "Name": "%s %s (%d)%s" % (s["model"], colour, year, (", " + s["Size"].strip()) if s["Size"] else ""),
                              "ProductNumber": "SY-%05d" % pid, "SellStartDate": rel, "SellEndDate": dt.date(year + 5, rel.month, 1) - dt.timedelta(days=1),
                              "base_date": rel, "base_price": self.list_price(s["ProductID"], rel), "base_cost": self.cost(s["ProductID"], rel)})
            out.append({"k": k, "date": rel, "model": model, "colour": colour, "products": prods})
        return out

    @functools.lru_cache(maxsize=None)
    def new_products(self, upto_year):
        return {p["ProductID"]: p for y in range(2014, upto_year + 1) for r in self.releases(y) for p in r["products"]}

    def product(self, pid, d=None):
        if pid in self.products:
            return self.products[pid]
        return self.new_products((d or dt.date(2100, 1, 1)).year if d else 2100)[pid] if d else self.new_products(2100)[pid]

    def active(self, d, channel):
        """[(pid, weight)] sellable on d. Originals until their model retires; new lines from release to SellEndDate."""
        key = "w_online" if channel == "online" else "w_reseller"
        out = []
        for p in self.P["products"]:
            if p[key] > 0 and (p["cat"] != 1 or not p["ProductModelID"] or self.retire_date(p["ProductModelID"]) >= d):
                out.append((p["ProductID"], p[key]))
        for p in self.new_products(d.year).values():
            if p["SellStartDate"] <= d <= p["SellEndDate"]:
                w = self.products[p["src"]][key] * 0.6
                if w > 0:
                    out.append((p["ProductID"], w))
        return out

    @staticmethod
    def rises(since, d):
        """Number of 1 July price changes in (since, d]."""
        n = d.year - since.year + (1 if d >= dt.date(d.year, 7, 1) else 0) - (1 if since >= dt.date(since.year, 7, 1) else 0)
        return max(0, n)

    def list_price(self, pid, d):
        p = self.products.get(pid) or self.new_products(d.year)[pid]
        base, since = (p["ListPrice"], ORIGIN) if pid in self.products else (p["base_price"], p["base_date"])
        return round(base * (1 + PRICE_RISE.get(p["cat"], 0)) ** self.rises(since, d), 2)

    def cost(self, pid, d):
        p = self.products.get(pid) or self.new_products(d.year)[pid]
        base, since = (p["StandardCost"], ORIGIN) if pid in self.products else (p["base_cost"], p["base_date"])
        return round(base * (1 + PRICE_RISE.get(p["cat"], 0)) ** self.rises(since, d), 4)

    # ---------------------------------------------------------------- offers
    @functools.lru_cache(maxsize=None)
    def offers(self, year):
        """Offers of a year: volume tiers (reseller, whole year), three seasonal sales, clearance of retiring models, launches."""
        b = 100 + (year - 2014) * 20; start = max(dt.date(year, 1, 1), ORIGIN); end = dt.date(year, 12, 31); out = []
        for i, (lo, hi, pct) in enumerate([(11, 14, .02), (15, 24, .05), (25, 40, .10), (41, 60, .15), (61, None, .20)]):
            out.append({"SpecialOfferID": b + i, "Description": "Volume Discount %s (%d)" % ("%d to %d" % (lo, hi) if hi else "over 60", year),
                        "DiscountPct": pct, "Type": "Volume Discount", "Category": "Reseller", "StartDate": start, "EndDate": end,
                        "MinQty": lo, "MaxQty": hi, "scope": "tier"})
        seasonal = [(5, "Spring Helmet Sale", .15, (4, 1), (5, 31), ("sub", 31)), (6, "Autumn Touring Sale", .10, (9, 15), (10, 31), ("sub", 3)),
                    (7, "Holiday Accessories Sale", .10, (11, 20), (12, 31), ("cat", 4))]
        for i, name, pct, (m1, d1), (m2, d2), scope in seasonal:
            s, e = dt.date(year, m1, d1), dt.date(year, m2, d2)
            if e >= ORIGIN:
                out.append({"SpecialOfferID": b + i, "Description": "%s (%d)" % (name, year), "DiscountPct": pct, "Type": "Seasonal Discount",
                            "Category": "Customer", "StartDate": max(s, ORIGIN), "EndDate": e, "MinQty": 0, "MaxQty": None, "scope": scope})
        retiring = sorted(m for m in self.models if self.retire_date(m).year == year)[:4]
        for i, m in enumerate(retiring):
            name = next(p["model"] for p in self.P["products"] if p["ProductModelID"] == m)
            out.append({"SpecialOfferID": b + 8 + i, "Description": "%s Clearance Sale (%d)" % (name, year), "DiscountPct": .30,
                        "Type": "Discontinued Product", "Category": "Customer", "StartDate": max(dt.date(year, 4, 1), ORIGIN),
                        "EndDate": self.retire_date(m), "MinQty": 0, "MaxQty": None, "scope": ("model", m)})
        for r in self.releases(year):
            out.append({"SpecialOfferID": b + 12 + r["k"], "Description": "%s %s Launch (%d)" % (self.products[r["products"][0]["src"]]["model"], r["colour"], year),
                        "DiscountPct": .15, "Type": "New Product", "Category": "Customer", "StartDate": r["date"],
                        "EndDate": r["date"] + dt.timedelta(days=60), "MinQty": 0, "MaxQty": None, "scope": ("new", r["k"])})
        return out

    def offer_products(self, o, year, d):
        """Products an offer covers, as known on day d (new lines released later in the year are added on their release day)."""
        sc = o["scope"]; prods = list(self.products.values()) + [p for p in self.new_products(year).values() if p["SellStartDate"] <= d]
        if sc == "tier":
            return [p["ProductID"] for p in prods if (p["w_reseller"] > 0) and (p["ProductID"] in self.products or p["SellStartDate"].year == year or p["SellStartDate"] <= dt.date(year, 1, 1))]
        if sc[0] == "sub":
            return [p["ProductID"] for p in prods if p["ProductSubcategoryID"] == sc[1] and (p["w_online"] or p["w_reseller"])]
        if sc[0] == "cat":
            return [p["ProductID"] for p in prods if p["cat"] == sc[1] and (p["w_online"] or p["w_reseller"])]
        if sc[0] == "model":
            return [p["ProductID"] for p in self.P["products"] if p["ProductModelID"] == sc[1] and (p["w_online"] or p["w_reseller"])]
        return [p["ProductID"] for r in self.releases(year) if r["k"] == sc[1] for p in r["products"]]

    @functools.lru_cache(maxsize=4096)
    def offer_map(self, d):
        """{pid: [(offer, products)]} of offers live on d."""
        m = collections.defaultdict(list)
        for o in self.offers(d.year):
            if o["StartDate"] <= d <= o["EndDate"]:
                for pid in self.offer_products(o, d.year, d):
                    m[pid].append(o)
        return m

    def online_offer(self, pid, d):
        best = None
        for o in self.offer_map(d).get(pid, []):
            if o["Category"] == "Customer" and (best is None or o["DiscountPct"] > best["DiscountPct"]):
                best = o
        return best

    def tier_offer(self, pid, qty, d):
        for o in self.offer_map(d).get(pid, []):
            if o["scope"] == "tier" and qty >= o["MinQty"] and (o["MaxQty"] is None or qty <= o["MaxQty"]):
                return o
        return None

    # ---------------------------------------------------------------- customers
    def new_customers(self, d):
        """The individual customers created on d (each places a first web order that day)."""
        r = self.rng("cust", self.idx(d)); P = self.P
        n = min(int(r.poisson(self.new_rate(d))), SLOT["cust"] - 1)
        out = []
        for i in range(n):
            t = self.territories[int(r.choice(len(self.territories), p=self.tshare))]
            pool = P["address_pool"][t]; city, spid, pc = pool[int(r.integers(len(pool)))]
            first = P["first_names"][int(r.integers(len(P["first_names"])))]; last = P["last_names"][int(r.integers(len(P["last_names"])))]
            key = 500000 + self.idx(d) * SLOT["cust"] + i
            out.append({"id": key, "territory": int(t), "first": first, "last": last, "middle": "ABCDEJLMRST"[int(r.integers(11))] if r.random() < .5 else None,
                        "email": "%s%d@adventure-works.com" % (first.lower().replace(" ", ""), int(r.integers(1, 100))),
                        "phone": "%03d-555-01%02d" % (int(r.integers(200, 999)), int(r.integers(0, 100))),
                        "line1": "%d %s" % (int(r.integers(1, 9999)), P["streets"][int(r.integers(len(P["streets"])))]),
                        "city": city, "spid": spid, "pc": pc, "promo": int(r.integers(0, 3)),
                        "birth": dt.date(int(r.integers(1940, 2004)), int(r.integers(1, 13)), int(r.integers(1, 29))),
                        "gender": "MF"[int(r.integers(2))], "marital": "MS"[int(r.integers(2))], "children": int(r.integers(0, 5)),
                        "income": ["0-25000", "25001-50000", "50001-75000", "75001-100000", "greater than 100000"][int(r.integers(5))],
                        "education": ["Bachelors ", "Graduate Degree", "High School", "Partial College", "Partial High School"][int(r.integers(5))],
                        "occupation": ["Clerical", "Management", "Manual", "Professional", "Skilled Manual"][int(r.integers(5))],
                        "home": int(r.integers(2)), "cars": int(r.integers(0, 5)),
                        "commute": ["0-1 Miles", "1-2 Miles", "2-5 Miles", "5-10 Miles", "10+ Miles"][int(r.integers(5))], "since": d})
        return out

    def cum_new(self):
        if self._cum_new is None:
            days = [ORIGIN + dt.timedelta(days=i) for i in range((dt.date(2041, 1, 1) - ORIGIN).days)]
            self._cum_new = np.cumsum([self.new_rate(x) for x in days])
        return self._cum_new

    def returning_customer(self, r, d):
        """A customer who ordered before d: an original web customer (profile pool) or a generated one from an earlier day."""
        P = self.P; n_orig = len(P["returning_pool"]); i = self.idx(d)
        n_syn = float(self.cum_new()[i - 1]) if i > 0 else 0.0
        for _ in range(20):
            if r.random() * (n_orig + n_syn) < n_orig:
                c = P["returning_pool"][int(r.integers(n_orig))]
                return {"id": c[0], "territory": c[1], "address": c[2]}
            j = bisect.bisect_left(self.cum_new(), r.random() * n_syn, 0, i)
            prev = self.new_customers(ORIGIN + dt.timedelta(days=j))
            if prev:
                c = prev[int(r.integers(len(prev)))]
                return {"id": c["id"], "territory": c["territory"], "address": c["id"]}
        c = P["returning_pool"][int(r.integers(n_orig))]
        return {"id": c[0], "territory": c[1], "address": c[2]}

    # ---------------------------------------------------------------- one day
    def day(self, d, end=None):
        end = end or d; b = Batch(); i = self.idx(d)
        if d < ORIGIN:
            raise ValueError("generated data starts %s" % ORIGIN)
        self._catalog(d, b)
        self._quotas(d, b)
        line = [10000000 + i * SLOT["line"]]; txn = [10000000 + i * SLOT["txn"]]
        self._online(d, end, b, line, txn)
        self._reseller(d, end, b, line, txn)
        self._reviews(d, b)
        if d >= WO_FROM:
            self._work_orders(d, b, txn)
        if d >= PO_FROM and d.weekday() == 0:
            self._purchase_orders(d, b, txn)
        # orders placed 7 days ago ship today (no-op when they were generated already shipped)
        ship_from = d - dt.timedelta(days=SHIP_DAYS)
        if ship_from >= ORIGIN:
            lo = 1000000 + self.idx(ship_from) * SLOT["order"]
            b.updates.append(("Sales.SalesOrderHeader", {"Status": 5, "ShipDate": d2s(d), "ModifiedDate": d2s(d)},
                              {"SalesOrderID_between": [lo, lo + SLOT["order"] - 1], "Status_lt": 5}))
        if len(txn) and txn[0] >= 10000000 + (i + 1) * SLOT["txn"]:
            raise RuntimeError("transaction slot overflow on %s" % d)
        return b

    def _catalog(self, d, b):
        y = d.year
        # offers are published on their start day; tiers on the first day of the year (or ORIGIN)
        for o in self.offers(y):
            if o["StartDate"] == d:
                b.add("Sales.SpecialOffer", {k: (d2s(v) if isinstance(v, dt.date) else v) for k, v in o.items() if k != "scope"} |
                      {"rowguid": guid("SpecialOffer", o["SpecialOfferID"]), "ModifiedDate": d2s(d)})
                for pid in sorted(self.offer_products(o, y, d)):
                    b.add("Sales.SpecialOfferProduct", {"SpecialOfferID": o["SpecialOfferID"], "ProductID": pid,
                                                        "rowguid": guid("SpecialOfferProduct", "%d-%d" % (o["SpecialOfferID"], pid)), "ModifiedDate": d2s(d)})
        for r in self.releases(y):
            if r["date"] != d:
                continue
            for p in r["products"]:
                pid = p["ProductID"]
                b.add("Production.Product", {"ProductID": pid, "Name": p["Name"], "ProductNumber": p["ProductNumber"], "MakeFlag": p["MakeFlag"],
                      "FinishedGoodsFlag": p["FinishedGoodsFlag"], "Color": p["Color"], "SafetyStockLevel": p["SafetyStockLevel"],
                      "ReorderPoint": p["ReorderPoint"], "StandardCost": p["base_cost"], "ListPrice": p["base_price"], "Size": p["Size"],
                      "SizeUnitMeasureCode": p["SizeUnitMeasureCode"], "WeightUnitMeasureCode": p["WeightUnitMeasureCode"], "Weight": p["Weight"],
                      "DaysToManufacture": p["DaysToManufacture"], "ProductLine": p["ProductLine"], "Class": p["Class"], "Style": p["Style"],
                      "ProductSubcategoryID": p["ProductSubcategoryID"], "ProductModelID": p["ProductModelID"], "SellStartDate": d2s(d),
                      "SellEndDate": d2s(p["SellEndDate"]), "DiscontinuedDate": None, "rowguid": guid("Product", pid), "ModifiedDate": d2s(d)})
                if p.get("photo"):
                    b.add("Production.ProductProductPhoto", {"ProductID": pid, "ProductPhotoID": p["photo"], "Primary": 1, "ModifiedDate": d2s(d)})
                for k, (comp, unit, level, qty) in enumerate(self.P["bom"].get(str(p["src"]), [])):
                    b.add("Production.BillOfMaterials", {"BillOfMaterialsID": 50000 + (pid - 5000) * 40 + k, "ProductAssemblyID": pid, "ComponentID": comp,
                          "StartDate": d2s(d), "EndDate": None, "UnitMeasureCode": unit, "BOMLevel": level, "PerAssemblyQty": qty, "ModifiedDate": d2s(d)})
                b.add("Production.ProductListPriceHistory", {"ProductID": pid, "StartDate": d2s(d), "EndDate": d2s(self._price_end(d)), "ListPrice": p["base_price"], "ModifiedDate": d2s(d)})
                b.add("Production.ProductCostHistory", {"ProductID": pid, "StartDate": d2s(d), "EndDate": d2s(self._price_end(d)), "StandardCost": p["base_cost"], "ModifiedDate": d2s(d)})
                b.add("Sales.SpecialOfferProduct", {"SpecialOfferID": 1, "ProductID": pid, "rowguid": guid("SpecialOfferProduct", "1-%d" % pid), "ModifiedDate": d2s(d)})
                for o in self.offers(y):   # offers already running this year that cover the new product
                    if o["StartDate"] < d <= o["EndDate"] and pid in self.offer_products(o, y, d):
                        b.add("Sales.SpecialOfferProduct", {"SpecialOfferID": o["SpecialOfferID"], "ProductID": pid,
                                                            "rowguid": guid("SpecialOfferProduct", "%d-%d" % (o["SpecialOfferID"], pid)), "ModifiedDate": d2s(d)})
        if d.month == 7 and d.day == 1 and d.year >= 2015:   # yearly price list
            for pid in sorted(set(self.products) | {p for p, x in self.new_products(y).items() if x["SellStartDate"] < d}):
                p = self.product(pid, d)
                if PRICE_RISE.get(p["cat"], 0) <= 0 or not (p.get("w_online") or p.get("w_reseller")):
                    continue
                if pid in self.products and p["cat"] == 1 and p["ProductModelID"] and self.retire_date(p["ProductModelID"]) < d:
                    continue
                if pid not in self.products and p["SellEndDate"] < d:
                    continue
                b.add("Production.ProductListPriceHistory", {"ProductID": pid, "StartDate": d2s(d), "EndDate": d2s(self._price_end(d)), "ListPrice": self.list_price(pid, d), "ModifiedDate": d2s(d)})
                b.add("Production.ProductCostHistory", {"ProductID": pid, "StartDate": d2s(d), "EndDate": d2s(self._price_end(d)), "StandardCost": self.cost(pid, d), "ModifiedDate": d2s(d)})

    @staticmethod
    def _price_end(d):
        return dt.date(d.year + (1 if d >= dt.date(d.year, 7, 1) else 0), 6, 30)

    def _quotas(self, d, b):
        if d.day != 1 or d.month not in (1, 4, 7, 10):
            return
        r = self.rng("quota", self.idx(d)); f = self.g(d) / self.g(dt.date(2014, 3, 1))
        for sp, q in self.P["quotas"]:
            b.add("Sales.SalesPersonQuotaHistory", {"BusinessEntityID": sp, "QuotaDate": d2s(d), "SalesQuota": round(q * f * float(r.uniform(.9, 1.1)), -3),
                                                    "rowguid": guid("Quota", "%d-%s" % (sp, d)), "ModifiedDate": d2s(d)})

    def _order(self, b, d, end, oid, cust, online, lines, line, txn, sp=None, store=None, r=None):
        shipped = d + dt.timedelta(days=SHIP_DAYS) <= end
        sub = 0.0
        for pid, qty, price, disc, offer in lines:
            sub += round(price * (1 - disc), 4) * qty
            lid = line[0]; line[0] += 1
            b.add("Sales.SalesOrderDetail", {"SalesOrderID": oid, "SalesOrderDetailID": lid, "CarrierTrackingNumber": None if online else
                  "%04X-%04X-%02X" % ((oid * 7919) % 65536, (lid * 104729) % 65536, lid % 256), "OrderQty": qty, "ProductID": pid,
                  "SpecialOfferID": offer, "UnitPrice": price, "UnitPriceDiscount": disc, "rowguid": guid("SOD", lid), "ModifiedDate": d2s(d)})
            b.add("Production.TransactionHistory", {"TransactionID": txn[0], "ProductID": pid, "ReferenceOrderID": oid, "ReferenceOrderLineID": lid,
                  "TransactionDate": d2s(d), "TransactionType": "S", "Quantity": qty, "ActualCost": price, "ModifiedDate": d2s(d)})
            txn[0] += 1
        sub = money(sub)
        b.add("Sales.SalesOrderHeader", {"SalesOrderID": oid, "RevisionNumber": 8, "OrderDate": d2s(d), "DueDate": d2s(d + dt.timedelta(days=DUE_DAYS)),
              "ShipDate": d2s(d + dt.timedelta(days=SHIP_DAYS)) if shipped else None, "Status": 5 if shipped else 1, "OnlineOrderFlag": 1 if online else 0,
              "PurchaseOrderNumber": None if online else "PO%011d" % ((oid * 2654435761) % 10 ** 11), "AccountNumber": ("10-4030-%06d" if online else "10-4020-%06d") % (cust["id"] if online else store),
              "CustomerID": cust["id"], "SalesPersonID": sp, "TerritoryID": cust["territory"], "BillToAddressID": cust["bill"], "ShipToAddressID": cust["ship"],
              "ShipMethodID": 1 if online else 5, "CreditCardID": None, "CreditCardApprovalCode": None, "CurrencyRateID": None,
              "SubTotal": sub, "TaxAmt": money(sub * TAX), "Freight": money(sub * FREIGHT), "Comment": None,
              "rowguid": guid("SOH", oid), "ModifiedDate": d2s(d + dt.timedelta(days=SHIP_DAYS)) if shipped else d2s(d)})

    def _basket(self, r, active, k):
        pids = np.array([a[0] for a in active]); w = np.array([a[1] for a in active], float); w /= w.sum()
        return [int(x) for x in r.choice(pids, size=min(k, len(pids)), replace=False, p=w)]

    def _online(self, d, end, b, line, txn):
        r = self.rng("online", self.idx(d)); P = self.P; base = 1000000 + self.idx(d) * SLOT["order"]
        news = self.new_customers(d)
        for c in news:   # generated customer: BusinessEntity, Person, e-mail, phone, address, customer row
            demo = ('<IndividualSurvey xmlns="http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/IndividualSurvey"><TotalPurchaseYTD>0</TotalPurchaseYTD>'
                    '<DateFirstPurchase>%sZ</DateFirstPurchase><BirthDate>%sZ</BirthDate><MaritalStatus>%s</MaritalStatus><YearlyIncome>%s</YearlyIncome>'
                    '<Gender>%s</Gender><TotalChildren>%d</TotalChildren><NumberChildrenAtHome>0</NumberChildrenAtHome><Education>%s</Education>'
                    '<Occupation>%s</Occupation><HomeOwnerFlag>%d</HomeOwnerFlag><NumberCarsOwned>%d</NumberCarsOwned><CommuteDistance>%s</CommuteDistance></IndividualSurvey>') % (
                d.isoformat(), c["birth"].isoformat(), c["marital"], c["income"], c["gender"], c["children"], c["education"], c["occupation"], c["home"], c["cars"], c["commute"])
            k = c["id"]
            b.add("Person.BusinessEntity", {"BusinessEntityID": k, "rowguid": guid("BE", k), "ModifiedDate": d2s(d)})
            b.add("Person.Person", {"BusinessEntityID": k, "PersonType": "IN", "NameStyle": 0, "Title": None, "FirstName": c["first"], "MiddleName": c["middle"],
                  "LastName": c["last"], "Suffix": None, "EmailPromotion": c["promo"], "AdditionalContactInfo": None, "Demographics": demo,
                  "rowguid": guid("Person", k), "ModifiedDate": d2s(d)})
            b.add("Person.EmailAddress", {"BusinessEntityID": k, "EmailAddressID": k, "EmailAddress": c["email"], "rowguid": guid("Email", k), "ModifiedDate": d2s(d)})
            b.add("Person.PersonPhone", {"BusinessEntityID": k, "PhoneNumber": c["phone"], "PhoneNumberTypeID": 1, "ModifiedDate": d2s(d)})
            b.add("Person.Address", {"AddressID": k, "AddressLine1": c["line1"], "AddressLine2": None, "City": c["city"], "StateProvinceID": c["spid"],
                  "PostalCode": c["pc"], "rowguid": guid("Address", k), "ModifiedDate": d2s(d)})
            b.add("Person.BusinessEntityAddress", {"BusinessEntityID": k, "AddressID": k, "AddressTypeID": 2, "rowguid": guid("BEA", k), "ModifiedDate": d2s(d)})
            b.add("Sales.Customer", {"CustomerID": k, "PersonID": k, "StoreID": None, "TerritoryID": c["territory"], "rowguid": guid("Customer", k), "ModifiedDate": d2s(d)})
        returning = int(r.poisson(self.online_rate(d) * (1 - P["online_new_customer_share"])))
        custs = [{"id": c["id"], "territory": c["territory"], "address": c["id"]} for c in news]
        rr = self.rng("returning", self.idx(d))
        custs += [self.returning_customer(rr, d) for _ in range(returning)]
        custs = custs[:SLOT["online_max"]]
        active = self.active(d, "online"); lines_k, lines_p = self.lines_on
        reasons = sorted(P["sales_reason_rate"].items(), key=lambda kv: int(kv[0]))
        for n, c in enumerate(custs):
            oid = base + n; k = int(r.choice(lines_k, p=lines_p)); lines = []
            for pid in self._basket(r, active, k):
                o = self.online_offer(pid, d)
                lines.append((pid, 1, self.list_price(pid, d), o["DiscountPct"] if o else 0.0, o["SpecialOfferID"] if o else 1))
            self._order(b, d, end, oid, {**c, "bill": c["address"], "ship": c["address"]}, True, lines, line, txn)
            got = False
            for rid, rate in reasons:
                if r.random() < rate:
                    got = True; b.add("Sales.SalesOrderHeaderSalesReason", {"SalesOrderID": oid, "SalesReasonID": int(rid), "ModifiedDate": d2s(d)})
            if not got:
                b.add("Sales.SalesOrderHeaderSalesReason", {"SalesOrderID": oid, "SalesReasonID": 1, "ModifiedDate": d2s(d)})

    def _reseller(self, d, end, b, line, txn):
        if (d + dt.timedelta(days=1)).day != 1:
            return   # reseller orders land on the last day of the month, as in 2011-2014
        r = self.rng("reseller", self.idx(d)); base = 1000000 + self.idx(d) * SLOT["order"] + SLOT["online_max"]
        n = min(int(r.poisson(self.P["reseller_orders_per_month"] * self.g(d))), SLOT["order"] - SLOT["online_max"], len(self.stores))
        picks = r.choice(len(self.stores), size=n, replace=False, p=self.store_w)
        active = self.active(d, "reseller"); lk, lp = self.lines_res; qk, qp = self.qty_res
        for j, s in enumerate(sorted(int(x) for x in picks)):
            cust_id, sp, terr, bill, ship, _ = self.stores[s]; lines = []
            for pid in self._basket(r, active, int(r.choice(lk, p=lp))):
                qty = int(r.choice(qk, p=qp)); o = self.tier_offer(pid, qty, d)
                price = round(self.list_price(pid, d) * self.P["reseller_price_ratio"][str(self.product(pid, d)["cat"])], 4)
                lines.append((pid, qty, price, o["DiscountPct"] if o else 0.0, o["SpecialOfferID"] if o else 1))
            if line[0] + len(lines) >= 10000000 + (self.idx(d) + 1) * SLOT["line"]:
                break
            self._order(b, d, end, base + j, {"id": cust_id, "territory": terr, "bill": bill, "ship": ship}, False, lines, line, txn, sp=sp, store=cust_id)

    def _reviews(self, d, b):
        r = self.rng("review", self.idx(d)); P = self.P
        active = self.active(d, "online")
        n = min(int(r.poisson(len(active) * 3 / 365.0)), SLOT["review"])
        ratings, rp = self.ratings
        for i, pid in enumerate(self._basket(r, active, n) if n else []):
            first = P["first_names"][int(r.integers(len(P["first_names"])))]; rating = int(r.choice(ratings, p=rp))
            b.add("Production.ProductReview", {"ProductReviewID": 50000 + self.idx(d) * SLOT["review"] + i, "ProductID": pid, "ReviewerName": first,
                  "ReviewDate": d2s(d), "EmailAddress": "%s%d@adventure-works.com" % (first.lower().replace(" ", ""), int(r.integers(1, 100))),
                  "Rating": rating, "Comments": REVIEW_TEXT[rating], "ModifiedDate": d2s(d)})

    def _work_orders(self, d, b, txn):
        """Work orders are written when they complete (EndDate = d), so every generated row is history."""
        r = self.rng("wo", self.idx(d)); P = self.P; base = 500000 + self.idx(d) * SLOT["wo"]; n = 0
        plan = [(int(pid), w) for pid, w in sorted(P["work_orders"].items(), key=lambda kv: int(kv[0]))]
        plan += [(pid, P["work_orders"][str(p["src"])]) for pid, p in sorted(self.new_products(d.year).items())
                 if str(p["src"]) in P["work_orders"] and p["SellStartDate"] + dt.timedelta(days=20) <= d <= p["SellEndDate"]]
        f = self.g(d)
        for pid, w in plan:
            p = self.products.get(pid) or self.new_products(d.year).get(pid)
            if p and p.get("cat") == 1 and pid in self.products and p["ProductModelID"] and self.retire_date(p["ProductModelID"]) < d:
                continue
            rate = w["per_day"] * f * (0.6 if pid >= 5000 else 1.0)
            for _ in range(int(r.poisson(rate))):
                if n >= SLOT["wo"]:
                    return
                wid = base + n; n += 1
                start = d - dt.timedelta(days=int(r.integers(10, 17)))
                qty = max(1, int(r.poisson(w["qty"])))
                scrap = 0; reason = None
                if r.random() < P["scrap"]["wo_share"]:
                    scrap = max(1, int(round(qty * P["scrap"]["qty_share"])))
                    reason = int(r.choice(self.scrap_ids, p=self.scrap_p))
                b.add("Production.WorkOrder", {"WorkOrderID": wid, "ProductID": pid, "OrderQty": qty, "ScrappedQty": scrap, "StartDate": d2s(start),
                      "EndDate": d2s(d), "DueDate": d2s(start + dt.timedelta(days=11)), "ScrapReasonID": reason, "ModifiedDate": d2s(d)})
                for seq, loc, hrs, cost, days in w["ops"]:
                    se = start + dt.timedelta(days=max(0, days or 0))
                    b.add("Production.WorkOrderRouting", {"WorkOrderID": wid, "ProductID": pid, "OperationSequence": seq, "LocationID": loc,
                          "ScheduledStartDate": d2s(start), "ScheduledEndDate": d2s(se), "ActualStartDate": d2s(start), "ActualEndDate": d2s(min(se + dt.timedelta(days=int(r.integers(0, 3))), d)),
                          "ActualResourceHrs": hrs, "PlannedCost": cost, "ActualCost": cost, "ModifiedDate": d2s(d)})
                b.add("Production.TransactionHistory", {"TransactionID": txn[0], "ProductID": pid, "ReferenceOrderID": wid, "ReferenceOrderLineID": 0,
                      "TransactionDate": d2s(start), "TransactionType": "W", "Quantity": qty, "ActualCost": 0, "ModifiedDate": d2s(d)})
                txn[0] += 1

    def _purchase_orders(self, d, b, txn):
        """Weekly (Mondays): purchase orders received this week, written complete (ordered lead-time days earlier)."""
        P = self.P; week = (d - PO_FROM).days // 7; r = self.rng("po", week); f = self.g(d) / self.g(dt.date(2014, 1, 1))
        by_vendor = collections.defaultdict(list)
        for pid, v, lt, sp, mn, mx, rate in self.vendor_lines:
            for _ in range(int(r.poisson(rate * f))):
                qty = int(r.integers(mn, (mx or mn) + 1)); qty = max(mn, qty - qty % max(1, mn))
                by_vendor[v].append((pid, lt, sp, qty))
        pod = 500000 + week * SLOT["pod"]
        for n, v in enumerate(sorted(by_vendor)[:SLOT["po"]]):
            lines = sorted(by_vendor[v])[:6]; lt = max(x[1] for x in lines)
            po = 500000 + week * SLOT["po"] + n; od = d - dt.timedelta(days=lt); sub = 0.0
            emp = P["po"]["employees"][int(r.integers(len(P["po"]["employees"])))]; sm = P["po"]["ship_methods"][int(r.integers(len(P["po"]["ship_methods"])))]
            rows = []
            for pid, _lt, sp, qty in lines:
                if pod >= 500000 + (week + 1) * SLOT["pod"]:
                    break
                price = round(sp * (1 + 0.02) ** self.rises(ORIGIN, d), 4); rej = int(r.binomial(qty, P["po"]["reject_rate"]))
                rows.append({"PurchaseOrderID": po, "PurchaseOrderDetailID": pod, "DueDate": d2s(d), "OrderQty": qty, "ProductID": pid, "UnitPrice": price,
                             "ReceivedQty": qty, "RejectedQty": rej, "ModifiedDate": d2s(d)})
                b.add("Production.TransactionHistory", {"TransactionID": txn[0], "ProductID": pid, "ReferenceOrderID": po, "ReferenceOrderLineID": pod,
                      "TransactionDate": d2s(od), "TransactionType": "P", "Quantity": qty, "ActualCost": price, "ModifiedDate": d2s(d)})
                txn[0] += 1; pod += 1; sub += price * qty
            if not rows:
                break
            sub = money(sub)
            b.add("Purchasing.PurchaseOrderHeader", {"PurchaseOrderID": po, "RevisionNumber": 1, "Status": 4, "EmployeeID": emp, "VendorID": v, "ShipMethodID": sm,
                  "OrderDate": d2s(od), "ShipDate": d2s(od + dt.timedelta(days=9 if lt > 9 else lt)), "SubTotal": sub, "TaxAmt": money(sub * TAX),
                  "Freight": money(sub * FREIGHT), "ModifiedDate": d2s(d)})
            for x in rows:
                b.add("Purchasing.PurchaseOrderDetail", x)

    # ---------------------------------------------------------------- ranges
    def range(self, start, end):
        b = Batch(); d = start
        while d <= end:
            b.extend(self.day(d, end)); d += dt.timedelta(days=1)
        return b


def apply_updates(batch):
    """Apply a batch's updates to its own rows in memory (tests: one run == day by day)."""
    by_id = {r["SalesOrderID"]: r for r in batch.rows.get("Sales.SalesOrderHeader", [])}
    for table, sets, where in batch.updates:
        lo, hi = where["SalesOrderID_between"]
        for oid in range(lo, hi + 1):
            r = by_id.get(oid)
            if r and r["Status"] < where["Status_lt"]:
                r.update(sets)
    batch.updates = []
    return batch


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--start", default=ORIGIN.isoformat()); ap.add_argument("--end", required=True)
    ap.add_argument("--seed", type=int, default=2026); ap.add_argument("--hash", action="store_true"); a = ap.parse_args()
    g = Generator(seed=a.seed); b = g.range(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end))
    out = {"counts": b.counts(), "rows": sum(b.counts().values())}
    if a.hash:
        out["sha256"] = apply_updates(b).digest()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
