"""Core transform. One Change (insert/update/delete of one SQL row) -> list of DynamoDB writes.

Ordering/idempotency: every item carries src_lsn (fixed-width hex position); puts are conditional on
`attribute_not_exists(PK) OR src_lsn < :pos`, so replays and older events are ignored.
Row shape (ADR 0005): the event's full row image + lookups of the related items already replicated to DynamoDB +
re-implemented computed columns/source_sql expressions (design/mapping/cdc-enrichment.yaml), so CDC and the bulk load
(which runs the mapping's source_sql) produce identical items without any SQL read. A referenced item that has not
arrived yet is retried briefly with backoff, then the event fails (Lambda batch retry -> DLQ; consumer DLQ).
"""
import base64, dataclasses, datetime, decimal, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (os.path.join(ROOT, "scripts", "loader"), HERE):  # repo layout, or Lambda package (awmap.py vendored next to us)
    if p not in sys.path:
        sys.path.insert(0, p)
import awmap  # noqa: E402  (Phase 3 mapping code, reused unchanged)

TOMBSTONE_TTL = 7 * 86400  # P3-4
META = {"PK", "SK", "src", "src_table", "src_pk", "src_lsn", "ver", "type", "derived"}


@dataclasses.dataclass
class Change:
    table: str                 # "Sales.SalesOrderHeader"
    op: str                    # "c" insert, "u" update, "d" delete, "r" read (snapshot)
    position: str              # "0x" + 20 hex digits (LSN), comparable as string
    before: dict = None        # column -> value (python types after normalisation)
    after: dict = None
    commit_ts_ms: int = None   # source commit time, for lag


def default_mapping_path():
    for p in (os.environ.get("AW_MAPPING"), os.path.join(ROOT, "design", "mapping", "mapping.json"), os.path.join(HERE, "mapping.json")):
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError("mapping.json")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_refresh_rules(path=None):
    import yaml
    for p in (path, os.path.join(ROOT, "design", "mapping", "cdc-refresh.yaml"), os.path.join(HERE, "cdc-refresh.yaml")):
        if p and os.path.exists(p):
            return yaml.safe_load(open(p))["rules"]
    return []


def lsn_from_debezium(change_lsn):
    """'0000002b:00000348:0002' -> '0x0000002b000003480002' (same 20-hex format as awmap.LOAD_LSN)."""
    return "0x" + change_lsn.replace(":", "").lower()


# ---------------------------------------------------------------- SQL Server types re-implemented (no SQL access)

_HID = [("000100", "..............0.....................0......0...0.1...", -281479271682120),
        ("000101", "...................0......0...0.1...", -4294971464), ("000110", ".....0...0.1...", -4168),
        ("0010", "..0.1...", -72), ("00111", "...", -8), ("01", "..", 0), ("100", "..", 4), ("101", "...", 8),
        ("110", "..0.1...", 16), ("1110", "...0...0.1...", 80), ("11110", ".....0...0.1...", 1104),
        ("111110", "...................0......0...0.1...", 5200),
        ("111111", "..............0.....................0......0...0.1...", 4294972496)]


def hid_levels(b):
    """hierarchyid binary (MS-SSCLRT 2.1.11 L/O/F triples) -> [[int, ...], ...] one list per level (dotted parts)."""
    bits = "".join(format(x, "08b") for x in bytes(b)).rstrip("0")
    i, out, cur = 0, [], []
    while i < len(bits):
        for pre, fmt, lo in _HID:
            if bits.startswith(pre, i):
                break
        else:
            raise ValueError("invalid hierarchyid 0x" + bytes(b).hex())
        i += len(pre); payload = ""
        for f in fmt:
            if f == ".":
                payload += bits[i]
            i += 1
        v = lo + int(payload, 2); last = bits[i] == "1"; i += 1
        cur.append(v if last else v - 1)  # F=0: followed by a dot, value stored +1
        if last:
            out.append(cur); cur = []
    return out


def _hid_bytes(v):
    if isinstance(v, str) and not v.startswith("/"):
        v = v.encode("latin-1")
    return v


def hid_to_string(v):
    """hierarchyid.ToString(); NULL -> None. Strings already in '/1/2/' form pass through."""
    v = _hid_bytes(v)
    if v is None or isinstance(v, str):
        return v
    return "/" + "".join(".".join(map(str, lv)) + "/" for lv in hid_levels(v))


def hid_level(v):
    v = _hid_bytes(v)
    if v is None:
        return None
    return v.strip("/").count("/") + 1 if isinstance(v, str) and v != "/" else (0 if isinstance(v, str) else len(hid_levels(v)))


def geo_point(v):
    """geography point -> (lat, long), like SpatialLocation.Lat/.Long (NULL for non-points).
    Accepts SQL Server CLR bytes (SRID, version, flags, lat, long), Debezium's {wkb, srid} struct, OGC WKB or WKT."""
    import struct
    if v is None:
        return None, None
    if isinstance(v, dict):
        v = v.get("wkb")
        v = base64.b64decode(v) if isinstance(v, str) else v
    if isinstance(v, str):
        m = re.match(r"\s*POINT\s*\(\s*([-0-9.eE]+)\s+([-0-9.eE]+)", v)
        return (float(m.group(2)), float(m.group(1))) if m else (None, None)
    v = bytes(v)
    if len(v) >= 21 and v[0] in (0, 1) and struct.unpack("<I" if v[0] else ">I", v[1:5])[0] & 0xFF == 1:  # WKB point (x=long, y=lat)
        x, y = struct.unpack("<dd" if v[0] else ">dd", v[5:21]); return y, x
    if len(v) >= 22 and v[5] & 0x08:  # CLR serialisation, single point
        return struct.unpack("<dd", v[6:22])
    return None, None


def _full_name(first, last):
    return first + " " + last if first is not None and last is not None else None


def _right(v, n, pad="0"):
    return None if v is None else (pad * n + str(v))[-n:]


def _q(v, places):
    return decimal.Decimal(v).quantize(decimal.Decimal(places)) if v is not None else None


def _sum_money(r):
    vals = [r.get(c) for c in ("SubTotal", "TaxAmt", "Freight")]
    return _q(sum(vals), "0.0001") if all(v is not None for v in vals) else decimal.Decimal("0.0000")


# SQL Server computed columns and source_sql expressions (CDC/DMS images never carry them), same types/scale/NULL rules.
# Functions run after the lookups, so they can use copied parent attributes (x_ columns are never stored).
COMPUTED = {
    "sod_line_total": lambda r: _q((r["UnitPrice"] * (decimal.Decimal("1.0") - r["UnitPriceDiscount"]) * r["OrderQty"]) if r["UnitPrice"] is not None else 0, "0.000001"),
    "pod_line_total": lambda r: _q((r["OrderQty"] * r["UnitPrice"]) if r["UnitPrice"] is not None else 0, "0.0001"),
    "pod_stocked_qty": lambda r: _q((r["ReceivedQty"] - r["RejectedQty"]) if r["ReceivedQty"] is not None else 0, "0.01"),
    "wo_stocked_qty": lambda r: (r["OrderQty"] - r["ScrappedQty"]) if r["OrderQty"] is not None else 0,
    "email_lower": lambda r: r["EmailAddress"].strip().lower() if r.get("EmailAddress") is not None else None,
    "card_last4": lambda r: r["CardNumber"][-4:] if r.get("CardNumber") is not None else None,
    "total_due": _sum_money,                                                         # SOH / POH TotalDue
    "so_number": lambda r: "SO%d" % r["SalesOrderID"],                               # SOH SalesOrderNumber
    "aw_account_number": lambda r: "AW" + _right(r["CustomerID"], 8),                # Customer AccountNumber (ufnLeadingZeros)
    "product_active": lambda r: "A" if r.get("SellEndDate") is None and r.get("DiscontinuedDate") is None else "X",
    "name_lower": lambda r: r["Name"].strip(" ").lower() if r.get("Name") is not None else None,
    "document_path": lambda r: hid_to_string(r.get("DocumentNode")),
    "document_level": lambda r: hid_level(r.get("DocumentNode")),
    # Employee: ISNULL(OrganizationNode.ToString(), '/'); a refresh rebuilds from the item (node omitted) -> keep org_path
    "org_path": lambda r: hid_to_string(r["OrganizationNode"]) if r.get("OrganizationNode") is not None else (r.get("org_path") or "/"),
    "org_level": lambda r: hid_level(r["OrganizationNode"]) if r.get("OrganizationNode") is not None else r.get("OrganizationLevel"),
    "bom_assembly": lambda r: "ROOT" if r.get("ProductAssemblyID") is None else _right(r["ProductAssemblyID"], 6),
    "customer_owner": lambda r: _right(r["PersonID"] if r.get("PersonID") is not None else r.get("StoreID"), 6),
    "person_name": lambda r: _full_name(r.get("x_first_name"), r.get("x_last_name")),
    "customer_display_name": lambda r: _full_name(r.get("x_first_name"), r.get("x_last_name")) or r.get("store_name"),
    "customer_sort_name": lambda r: (r["x_last_name"] + ", " + r["x_first_name"] if r.get("x_first_name") is not None and r.get("x_last_name") is not None
                                     else r.get("store_name") or "").upper() or None,
    "latitude": lambda r: geo_point(r.get("SpatialLocation"))[0],
    "longitude": lambda r: geo_point(r.get("SpatialLocation"))[1],
}


# ---------------------------------------------------------------- enrichment (image / lookup in DynamoDB)

def load_enrichment(path=None):
    import yaml
    for p in (path, os.path.join(ROOT, "design", "mapping", "cdc-enrichment.yaml"), os.path.join(HERE, "cdc-enrichment.yaml")):
        if p and os.path.exists(p):
            return yaml.safe_load(open(p))
    return {"lookup": {}}


class MissingParent(LookupError):
    """A referenced item is not (yet) in DynamoDB after the bounded retry: the event fails (Lambda: partial batch failure ->
    Kinesis retry -> DLQ; local consumer: retried in order, then parked in its DLQ state)."""


def _template_cols(*templates):
    return [m.group(1) for t in templates if t for m in awmap._FIELD.finditer(str(t))]


class Enricher:
    """Builds the mapping row for a change from the event's full row image plus GetItem/Query lookups of the related items
    already replicated to DynamoDB, plus re-implemented computed columns (design/mapping/cdc-enrichment.yaml).
    No SQL access. lookup: sink with get(table, pk, sk) and query(table, pk, index=, sk=, sk_begins=).
    A referenced item that has not arrived yet is retried `attempts` times with exponential backoff, then MissingParent."""

    def __init__(self, mapping, lookup, config=None, attempts=None, backoff_ms=None, sleep=time.sleep):
        self.m, self.lookup = mapping, lookup
        self.cfg = config if config is not None else load_enrichment()
        self.attempts = int(attempts if attempts is not None else os.environ.get("CDC_LOOKUP_ATTEMPTS", "4"))
        self.backoff_ms = float(backoff_ms if backoff_ms is not None else os.environ.get("CDC_LOOKUP_BACKOFF_MS", "100"))
        self.sleep = sleep
        self.stats = {"image": 0, "lookup": 0, "retries": 0, "missing": 0}

    def mode(self, table):
        return "lookup" if table in (self.cfg.get("lookup") or {}) else "image"

    def column_types(self, table):
        """Types for event normalisation, from mapping.json (no SQL needed)."""
        return [{"name": c["column"], "st": c["sql_type"]} for c in self.m["sources"][table].get("columns", [])]

    def current(self, table, image):
        """Row for an insert/update image: every referenced item must exist (bounded retry, then MissingParent)."""
        self.stats[self.mode(table)] += 1
        return self._build(table, image, strict=True)

    def from_image(self, table, image):
        """Row for a delete / before image: only the keys matter, so missing parents just leave copies empty."""
        return self._build(table, image, strict=False)

    def rebuild(self, table, image):
        """Row for a snapshot refresh (no retry: the dependent is skipped if one of its other parents is missing)."""
        return self._build(table, image, strict=True, attempts=1)

    def _build(self, table, image, strict, attempts=None):
        row = dict(image)
        spec = (self.cfg.get("lookup") or {}).get(table)
        if not spec:
            return row
        for lk in spec.get("lookups") or []:
            self._lookup(table, lk, row, strict, attempts or self.attempts)
        for col, fn in (spec.get("computed") or {}).items():
            row[col] = COMPUTED[fn](row)
        return row

    def _fetch(self, lk, row):
        pk = awmap.render(lk["PK"], row)
        if lk.get("index"):
            sk = awmap.render(lk["SK"], row) if lk.get("SK") else None
            items = self.lookup.query(lk["table"], pk, index=lk["index"], sk=sk)
            return items[0] if items else None
        return self.lookup.get(lk["table"], pk, awmap.render(lk["SK"], row))

    def _lookup(self, table, lk, row, strict, attempts):
        if "sum" in lk:  # aggregate over child items (absent children -> 0, like ISNULL(SUM(..),0))
            items = self.lookup.query(lk["table"], awmap.render(lk["PK"], row), sk_begins=awmap.render(lk["SK_begins"], row))
            row[lk["sum"]["col"]] = sum(int(i.get(lk["sum"]["attr"]) or 0) for i in items)
            return
        if any(row.get(c) is None for c in _template_cols(lk.get("PK"), lk.get("SK"))):
            # NULL foreign key (LEFT JOIN in the bulk load's source_sql): nothing to copy
            for col in (lk.get("attrs") or {}):
                row[col] = None
            if "exists" in lk:
                row[lk["exists"]] = 0
            return
        if "exists" in lk:  # EXISTS flag (e.g. x_is_vendor); tombstones count, so deletes still find the copy to tombstone
            pk, sk = awmap.render(lk["PK"], row), awmap.render(lk["SK"], row)
            row[lk["exists"]] = 1 if self.lookup.get(lk["table"], pk, sk, include_deleted=True) is not None else 0
            return
        item = None
        tries = attempts if strict else 1
        for attempt in range(tries):
            item = self._fetch(lk, row)
            if item is not None:
                break
            if attempt + 1 < tries:
                self.stats["retries"] += 1
                self.sleep(self.backoff_ms * (2 ** attempt) / 1000.0)
        if item is None:
            if strict:
                self.stats["missing"] += 1
                raise MissingParent("%s: referenced item %s %s/%s not in DynamoDB yet" % (
                    table, lk["table"], awmap.render(lk["PK"], row), awmap.render(lk["SK"], row) if lk.get("SK") else "*"))
            item = {}
        for col, attr in (lk.get("attrs") or {}).items():
            row[col] = item.get(attr)


_TO_INT = {"int", "smallint", "tinyint", "bigint"}


def image_from_item(mapping, table, item):
    """Inverse of awmap.business_attrs for a snapshot refresh: the dependent's own replicated item -> event-like image
    (base columns with SQL-ish Python types; derived attributes kept so refresh can fall back to them)."""
    src = mapping["sources"][table]
    row = {}
    for c in src.get("columns", []):
        v = item.get(awmap.attr(c["column"]))
        st = c["sql_type"]
        if v is not None:
            if st in _TO_INT or (st in ("bit",) and not isinstance(v, bool)):
                v = int(v) if st != "bit" else bool(v)
            elif st in ("float", "real"):
                v = float(v)
            elif st in ("datetime", "datetime2", "smalldatetime") and isinstance(v, str):
                v = datetime.datetime.fromisoformat(v)
            elif st == "date" and isinstance(v, str):
                v = datetime.date.fromisoformat(v[:10])
            elif st == "time" and isinstance(v, str):
                v = datetime.time.fromisoformat(v)
            elif st in ("varbinary", "binary", "image", "timestamp") and not isinstance(v, (bytes, bytearray)):
                v = bytes(v.value if hasattr(v, "value") else v)
        row[c["column"]] = v
    for d in src.get("derived_attributes") or []:
        if d in item:
            row.setdefault(d, item[d])
    return row


# ---------------------------------------------------------------- transform

class Transformer:
    """Turns Changes into writes against a sink (DynamoDBSink or MemorySink)."""

    def __init__(self, rows, sink, mapping=None, rules=None, clock=time.time):
        self.m = mapping or load_json(default_mapping_path())
        self.rows, self.sink, self.clock = rows, sink, clock
        self.rules = rules if rules is not None else load_refresh_rules()

    def items(self, table, row, position, now):
        src = self.m["sources"][table]
        return awmap.items_for_row(table, src, row, src["primary_key"], position, now)

    def apply(self, ch):
        """Returns a report dict: {'row': sql row, 'puts': [(table,item)], 'tombstones': [...], 'refreshed': n, 'skipped': n}."""
        if ch.table not in self.m["sources"]:
            return {"ignored": True}
        now = datetime.datetime.utcfromtimestamp(self.clock()).replace(microsecond=0).isoformat() + "Z"
        rep = {"puts": [], "tombstones": [], "refreshed": 0, "skipped": 0, "row": None}
        new_items, old_items = [], []
        if ch.op in ("c", "u", "r"):
            row = self.rows.current(ch.table, ch.after)
            if row is None:  # row already deleted again; the delete event follows and tombstones it
                row = self.rows.from_image(ch.table, ch.after)
            rep["row"] = row
            new_items = self.items(ch.table, row, ch.position, now)
        if ch.op == "d" or (ch.op == "u" and ch.before):
            img = ch.before or {}
            old_row = self.rows.from_image(ch.table, img)
            if ch.op == "d":
                rep["row"] = old_row
            try:
                old_items = self.items(ch.table, old_row, ch.position, now)
            except KeyError:
                old_items = []
        new_keys = {(t, i["PK"], i["SK"]) for t, i in new_items}
        for t, item in new_items:
            if self.sink.put(t, item, ch.position):
                rep["puts"].append((t, item))
            else:
                rep["skipped"] += 1
        # deletes, and items whose keys moved on update (e.g. a derived PO-number item) -> tombstones (D10, TTL P3-4)
        for t, item in old_items:
            if (t, item["PK"], item["SK"]) in new_keys:
                continue
            tomb = tombstone(item, ch.table, ch.position, now, int(self.clock()))
            if self.sink.put(t, tomb, ch.position):
                rep["tombstones"].append((t, tomb))
            else:
                rep["skipped"] += 1
        if ch.op in ("u", "d"):
            rep["refreshed"] = self.refresh(ch, now)
        return rep

    def copy_attrs(self, table):
        return _copy_attrs(self.m, table)

    def refresh(self, ch, now):
        """Snapshot-copy refresh (design/mapping/cdc-refresh.yaml): find the dependent items in DynamoDB, rebuild their rows
        from the items themselves + lookups (the changed parent is already written), update copies in place."""
        img = ch.after or ch.before
        n = 0
        for r in self.rules:
            if r["changed"] != ch.table:
                continue
            copies = self.copy_attrs(r["refresh"])
            seen = set()
            for dep in self.find(r, img):
                if dep.get("src_table") != r["refresh"] or dep.get("deleted") or dep.get("derived") or dep["src_pk"] in seen:
                    continue
                seen.add(dep["src_pk"])
                try:
                    row = self.rows.rebuild(r["refresh"], image_from_item(self.m, r["refresh"], dep))
                except MissingParent:
                    continue
                for t, item in self.items(r["refresh"], row, None, now):
                    # copied attributes whose source became NULL are absent from the new item -> REMOVE them
                    n += self.sink.refresh(t, item, remove=[a for a in copies if a not in item])
        return n

    def find(self, rule, img):
        """Dependent items for a refresh rule: a chain of Query/GetItem steps (each step's templates use the previous
        step's item, the first uses the changed row's image) or a filtered Scan for rare, unindexed parents."""
        level = [img]
        for i, st in enumerate(rule["find"]):
            nxt = []
            for ctx in level:
                if "scan" in st:
                    if any(ctx.get(c) is None for c in (st.get("match") or {}).values()):
                        continue
                    nxt += self.sink.scan(st["table"], dict(st["scan"], **{a: ctx[c] for a, c in (st.get("match") or {}).items()}))
                    continue
                try:
                    pk = awmap.render(st["PK"], ctx)
                    if st.get("SK") and not st.get("index"):
                        it = self.sink.get(st["table"], pk, awmap.render(st["SK"], ctx)); nxt += [it] if it else []
                    else:
                        nxt += self.sink.query(st["table"], pk, index=st.get("index"), sk_begins=awmap.render(st["SK_begins"], ctx) if st.get("SK_begins") else None)
                except KeyError:
                    continue
            level = nxt
        return level


def _copy_attrs(mapping, table):
    out = []
    for sn in mapping["sources"][table].get("snapshots") or []:
        out += [a for a in sn.get("attrs", []) if "*" not in a]
    return out


def tombstone(item, table, position, now, now_epoch):
    return {"PK": item["PK"], "SK": item["SK"], "type": item["type"], "deleted": True, "deleted_at": now,
            "ttl": now_epoch + TOMBSTONE_TTL, "ver": item.get("ver", 1) + 1, "src": "sql", "src_table": table,
            "src_pk": item["src_pk"], "src_lsn": position, "updated_at": now}


# ---------------------------------------------------------------- sinks

class DynamoDBSink:
    def __init__(self, resource):
        self.r = resource

    def get(self, table, pk, sk, include_deleted=False):
        """Lookup for enrichment (strongly consistent: the parent may have been written a moment ago); tombstones count
        as missing unless include_deleted."""
        it = self.r.Table(table).get_item(Key={"PK": pk, "SK": sk}, ConsistentRead=True).get("Item")
        return None if it is None or (it.get("deleted") and not include_deleted) else it

    def query(self, table, pk, index=None, sk=None, sk_begins=None):
        """Live items under a partition (base table or GSI1/GSI2, eventually consistent), optionally by SK / SK prefix."""
        from boto3.dynamodb.conditions import Key
        kp, ks = (index + "PK", index + "SK") if index else ("PK", "SK")
        cond = Key(kp).eq(pk)
        if sk is not None:
            cond = cond & Key(ks).eq(sk)
        elif sk_begins:
            cond = cond & Key(ks).begins_with(sk_begins)
        kw = {"KeyConditionExpression": cond}
        if index:
            kw["IndexName"] = index
        else:
            kw["ConsistentRead"] = True
        out, t = [], self.r.Table(table)
        while True:
            r = t.query(**kw)
            out += [i for i in r["Items"] if not i.get("deleted")]
            if "LastEvaluatedKey" not in r:
                return out
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    def scan(self, table, equals):
        """Filtered scan (only for rare refreshes of unindexed parents, e.g. a territory rename)."""
        from boto3.dynamodb.conditions import Attr
        cond = None
        for k, v in equals.items():
            c = Attr(k).eq(v); cond = c if cond is None else cond & c
        out, t, kw = [], self.r.Table(table), {"FilterExpression": cond}
        while True:
            r = t.scan(**kw)
            out += [i for i in r["Items"] if not i.get("deleted")]
            if "LastEvaluatedKey" not in r:
                return out
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    def put(self, table, item, position):
        t = self.r.Table(table)
        try:
            t.put_item(Item=item, ConditionExpression="attribute_not_exists(PK) OR src_lsn < :p", ExpressionAttributeValues={":p": position})
            return True
        except t.meta.client.exceptions.ConditionalCheckFailedException:
            return False

    def refresh(self, table, item, remove=()):
        """Snapshot copy refresh: SET non-key attributes in place and REMOVE copied attributes whose source is now NULL;
        never resurrects tombstones, never moves src_lsn."""
        t = self.r.Table(table)
        attrs = {k: v for k, v in item.items() if k not in META and k != "updated_at"}
        if not attrs and not remove:
            return 0
        names = {"#a%d" % i: k for i, k in enumerate(attrs)}
        names.update({"#r%d" % i: k for i, k in enumerate(remove)})
        values = {":v%d" % i: v for i, v in enumerate(attrs.values())}
        values[":u"] = item["updated_at"]
        expr = "SET " + ", ".join(["#a%d = :v%d" % (i, i) for i in range(len(attrs))] + ["updated_at = :u"])
        if remove:
            expr += " REMOVE " + ", ".join("#r%d" % i for i in range(len(remove)))
        try:
            t.update_item(Key={"PK": item["PK"], "SK": item["SK"]}, UpdateExpression=expr, ExpressionAttributeNames=names,
                          ExpressionAttributeValues=values, ConditionExpression="attribute_exists(PK) AND attribute_not_exists(deleted)")
            return 1
        except t.meta.client.exceptions.ConditionalCheckFailedException:
            return 0


class MemorySink:
    """Same semantics as DynamoDBSink, in memory (unit tests)."""

    def __init__(self):
        self.tables = {}

    def get(self, table, pk, sk, include_deleted=False):
        it = self.tables.get(table, {}).get((pk, sk))
        return None if it is None or (it.get("deleted") and not include_deleted) else it

    def raw(self, table, pk, sk):
        return self.tables.get(table, {}).get((pk, sk))

    def query(self, table, pk, index=None, sk=None, sk_begins=None):
        kp, ks = (index + "PK", index + "SK") if index else ("PK", "SK")
        out = [i for i in self.tables.get(table, {}).values() if not i.get("deleted") and i.get(kp) == pk
               and (sk is None or i.get(ks) == sk) and (not sk_begins or str(i.get(ks, "")).startswith(sk_begins))]
        return sorted(out, key=lambda i: str(i.get(ks)))

    def scan(self, table, equals):
        return [i for i in self.tables.get(table, {}).values() if not i.get("deleted") and all(i.get(k) == v for k, v in equals.items())]

    def put(self, table, item, position):
        cur = self.raw(table, item["PK"], item["SK"])
        if cur is not None and not cur.get("src_lsn", "") < position:
            return False
        self.tables.setdefault(table, {})[(item["PK"], item["SK"])] = dict(item)
        return True

    def refresh(self, table, item, remove=()):
        cur = self.tables.get(table, {}).get((item["PK"], item["SK"]))
        if cur is None or cur.get("deleted"):
            return 0
        cur.update({k: v for k, v in item.items() if k not in META})
        for a in remove:
            cur.pop(a, None)
        return 1


# ---------------------------------------------------------------- event normalisation

def _from_debezium_value(v, typ):
    if v is None:
        return None
    if typ in ("datetime", "datetime2", "smalldatetime"):
        return datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=v) if isinstance(v, int) else v
    if typ == "date":
        return (datetime.date(1970, 1, 1) + datetime.timedelta(days=v)) if isinstance(v, int) else v
    if typ in ("decimal", "numeric", "money", "smallmoney"):
        return decimal.Decimal(str(v))
    if typ in ("varbinary", "binary", "image", "timestamp", "hierarchyid", "geography", "geometry"):
        return base64.b64decode(v) if isinstance(v, str) else v
    if typ == "bit":
        return bool(v)
    return _common_value(v, typ)


def _common_value(v, typ):
    """Make image values look like the pymssql values the bulk loader sees (image-mode tables have no SQL re-read)."""
    if typ == "uniqueidentifier":
        return str(v).lower()          # Debezium/DMS send upper-case GUIDs; pymssql's UUID renders lower-case
    if typ == "time":
        if isinstance(v, int):         # Debezium connect mode: ms since midnight
            return (datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=v)).time()
        if isinstance(v, str):         # DMS: '07:00:00.0000000'
            return datetime.time.fromisoformat(v[:15] if "." in v else v)
    return v


def from_debezium(event, column_types):
    """Debezium (json, schemas disabled, time.precision.mode=connect, decimal.handling.mode=string,
    binary.handling.mode=base64) value -> Change. column_types: callable(table) -> [{'name','st'}]."""
    p = event.get("payload", event)
    src = p["source"]
    table = "%s.%s" % (src["schema"], src["table"])
    types = {c["name"]: c["st"] for c in column_types(table)}
    conv = lambda img: None if img is None else {k: _from_debezium_value(v, types.get(k)) for k, v in img.items()}
    return Change(table=table, op=p["op"], position=lsn_from_debezium(src["change_lsn"]), before=conv(p.get("before")),
                  after=conv(p.get("after")), commit_ts_ms=src.get("ts_ms"))


def from_dms(record, column_types):
    """AWS DMS -> Kinesis JSON message. The task adds column AR_H_CHANGE_SEQ (transformation rule) as the position;
    it is a 35-digit increasing number, re-encoded as fixed-width hex so it sorts like the local LSN format."""
    md, data = record["metadata"], dict(record["data"])
    table = "%s.%s" % (md["schema-name"], md["table-name"])
    op = {"insert": "c", "update": "u", "delete": "d", "load": "r"}[md["operation"]]
    seq = data.pop("ar_h_change_seq", None) or data.pop("AR_H_CHANGE_SEQ", None) or "0"
    position = "0x%030x" % int(seq)
    before = record.get("before-image")  # requires BeforeImageSettings in the task
    types = {c["name"]: c["st"] for c in column_types(table)}
    conv = lambda img: None if img is None else {k: _dms_value(v, types.get(k)) for k, v in img.items()}
    ts = md.get("timestamp")
    ts_ms = int(datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000) if ts else None
    after = conv(data) if op != "d" else None
    return Change(table=table, op=op, position=position, before=conv(before) if before else (conv(data) if op == "d" else None),
                  after=after, commit_ts_ms=ts_ms)


def _dms_value(v, typ):
    if v is None:
        return None
    if typ in ("datetime", "datetime2", "smalldatetime") and isinstance(v, str):
        return datetime.datetime.fromisoformat(v.replace("Z", ""))
    if typ == "date" and isinstance(v, str):
        return datetime.date.fromisoformat(v[:10])
    if typ in ("decimal", "numeric", "money", "smallmoney"):
        return decimal.Decimal(str(v))
    if typ in ("varbinary", "binary", "hierarchyid", "geography", "geometry") and isinstance(v, str):
        return base64.b64decode(v)
    if typ == "bit" and isinstance(v, (int, str)):
        return str(v).lower() in ("1", "true")
    return _common_value(v, typ)
