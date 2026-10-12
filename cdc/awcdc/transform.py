"""Core transform. One Change (insert/update/delete of one SQL row) -> list of DynamoDB writes.

Ordering/idempotency: every item carries src_lsn (fixed-width hex position); puts are conditional on
`attribute_not_exists(PK) OR src_lsn < :pos`, so replays and older events are ignored.
Row shape: inserts/updates re-read the row through the mapping's source_sql (same query as the bulk loader, so CDC and
bulk load produce identical items). Deletes and before-images are evaluated by running the same source_sql with the base
table replaced by the event image, so joined/computed key columns are available even though the row is gone.
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


# ---------------------------------------------------------------- SQL row access

def _base_alias(sql, table):
    m = re.search(r"FROM\s+" + re.escape(table) + r"(?![\w.])(\s+(?:AS\s+)?(?!JOIN|LEFT|WHERE|INNER)(\w+))?", sql, re.I)
    return m


class SqlRows:
    """Reads rows exactly like the bulk loader (awmap source_sql). conn: DB-API connection returning dict rows (pymssql as_dict)."""

    def __init__(self, conn, mapping):
        self.conn, self.m = conn, mapping
        self._types = {}

    def query(self, table):
        src = self.m["sources"][table]
        return src.get("source_sql") or "SELECT * FROM %s" % table

    def pk(self, table):
        return self.m["sources"][table]["primary_key"]

    def _run(self, sql, params):
        cur = self.conn.cursor(); cur.execute(sql, tuple(params)); return cur.fetchall()

    def by_columns(self, table, values):
        """Current rows of `table` (source_sql output) where output columns equal values."""
        conds, params = [], []
        for c, v in values.items():
            if isinstance(v, (bytes, bytearray)):  # binary keys (hierarchyid DocumentNode): inline literal, compare as varbinary
                conds.append("CAST(q.[%s] AS varbinary(892)) = %s" % (c, "0x" + bytes(v).hex() if v else "0x"))
            else:
                conds.append("q.[%s] = %%s" % c); params.append(v)
        return self._run("SELECT * FROM (%s) q WHERE %s" % (self.query(table), " AND ".join(conds)), params)

    def current(self, table, image):
        rows = self.by_columns(table, {c: image[c] for c in self.pk(table)})
        return rows[0] if rows else None

    def column_types(self, table):
        if table not in self._types:
            s, t = table.split(".")
            rows = self._run("""SELECT c.name, TYPE_NAME(c.user_type_id) AS t, COALESCE(TYPE_NAME(c.system_type_id), TYPE_NAME(c.user_type_id)) AS st,
                                       c.max_length, c.precision, c.scale, c.is_computed, cc.definition
                                FROM sys.columns c LEFT JOIN sys.computed_columns cc ON cc.object_id = c.object_id AND cc.column_id = c.column_id
                                WHERE c.object_id = OBJECT_ID(%s) ORDER BY c.column_id""", [s + "." + t])
            self._types[table] = rows
        return self._types[table]

    def from_image(self, table, image):
        """Run source_sql with the base table replaced by the image (for deletes / before images)."""
        cols, params, computed = [], [], []
        for c in self.column_types(table):
            n, st = c["name"], c["st"]
            if c["is_computed"]:  # CDC does not capture computed columns: recompute from the definition
                computed.append("%s AS [%s]" % (c["definition"], n)); continue
            v = image.get(n)
            if isinstance(v, str) and st in ("hierarchyid", "geography", "geometry") and not v.startswith("/"):
                v = v.encode("latin-1")  # raw CLR bytes delivered as a string by some drivers
            if isinstance(v, (bytes, bytearray)) or (v is None and st in ("hierarchyid", "geography", "geometry")):
                lit = "NULL" if v is None else ("hierarchyid::GetRoot()" if st == "hierarchyid" and not v else "0x" + bytes(v).hex())
                cols.append("CAST(%s AS %s) AS [%s]" % (lit, _sql_type(c), n))
            else:
                cols.append("CAST(%%s AS %s) AS [%s]" % (_sql_type(c), n)); params.append(v)
        derived = "(SELECT %s)" % ", ".join(cols)
        if computed:
            derived = "(SELECT z.*, %s FROM %s z)" % (", ".join(computed), derived)
        sql = self.query(table)
        m = _base_alias(sql, table)
        if m is None:
            raise ValueError("cannot find base table in source_sql of " + table)
        alias = m.group(2) or table.split(".")[1]
        sql = sql[:m.start()] + "FROM %s AS %s" % (derived, alias) + sql[m.end():]
        # parent rows may be gone too (cascading delete in the same transaction): keep the row with LEFT JOINs
        sql_left = re.sub(r"(?<!LEFT )(?<!OUTER )\bJOIN\b", "LEFT JOIN", sql)
        rows = self._run(sql_left, params)
        return rows[0] if rows else dict(image)


def _sql_type(c):
    st = c["st"]
    if st in ("nvarchar", "varchar", "nchar", "char", "varbinary", "binary"):
        n = c["max_length"]
        if n == -1:
            return st + "(max)"
        return "%s(%d)" % (st, n // 2 if st.startswith("n") else n)
    if st in ("decimal", "numeric"):
        return "%s(%d,%d)" % (st, c["precision"], c["scale"])
    if st in ("datetime2", "datetimeoffset", "time"):
        return "%s(%d)" % (st, c["scale"])
    return st


# ---------------------------------------------------------------- enrichment (image / lookup / sql)

def load_enrichment(path=None):
    import yaml
    for p in (path, os.path.join(ROOT, "design", "mapping", "cdc-enrichment.yaml"), os.path.join(HERE, "cdc-enrichment.yaml")):
        if p and os.path.exists(p):
            return yaml.safe_load(open(p))
    return {"lookup": {}, "sql": []}


def _q(v, places):
    return decimal.Decimal(v).quantize(decimal.Decimal(places)) if v is not None else None


# SQL Server computed columns (CDC/DMS images never include them), re-implemented with the same types/scale.
COMPUTED = {
    "sod_line_total": lambda r: _q((r["UnitPrice"] * (decimal.Decimal("1.0") - r["UnitPriceDiscount"]) * r["OrderQty"]) if r["UnitPrice"] is not None else 0, "0.000001"),
    "pod_line_total": lambda r: _q((r["OrderQty"] * r["UnitPrice"]) if r["UnitPrice"] is not None else 0, "0.0001"),
    "pod_stocked_qty": lambda r: _q((r["ReceivedQty"] - r["RejectedQty"]) if r["ReceivedQty"] is not None else 0, "0.01"),
    "wo_stocked_qty": lambda r: (r["OrderQty"] - r["ScrappedQty"]) if r["OrderQty"] is not None else 0,
    "email_lower": lambda r: r["EmailAddress"].strip().lower() if r.get("EmailAddress") is not None else None,
    "card_last4": lambda r: r["CardNumber"][-4:] if r.get("CardNumber") is not None else None,
}


class Enricher:
    """Builds the mapping row for a change: from the image, image + DynamoDB lookups, or a SQL re-read
    (design/mapping/cdc-enrichment.yaml). sql_rows: SqlRows or None. lookup: object with get(table, pk, sk)."""

    def __init__(self, mapping, lookup, sql_rows=None, config=None, force=None):
        self.m, self.lookup, self.sql = mapping, lookup, sql_rows
        self.cfg = config if config is not None else load_enrichment()
        self.force = force if force is not None else os.environ.get("CDC_ENRICHMENT")
        self.stats = {"image": 0, "lookup": 0, "sql": 0}

    def mode(self, table):
        if self.force:
            return self.force
        if table in (self.cfg.get("lookup") or {}):
            return "lookup"
        if table in (self.cfg.get("sql") or []) or self.m["sources"][table].get("source_sql"):
            return "sql"
        return "image"

    def column_types(self, table):
        """Types for event normalisation: from SQL if connected, else from mapping.json (no SQL needed)."""
        if self.sql:
            return self.sql.column_types(table)
        return [{"name": c["column"], "st": c["sql_type"]} for c in self.m["sources"][table].get("columns", [])]

    def by_columns(self, table, values):
        if not self.sql:
            raise RuntimeError("snapshot refresh needs SQL read access (%s)" % table)
        return self.sql.by_columns(table, values)

    def current(self, table, image):
        mode = self.mode(table); self.stats[mode] += 1
        if mode == "sql":
            return self.sql.current(table, image) if self.sql else None
        return self._build(table, image, mode)

    def from_image(self, table, image):
        if self.mode(table) == "sql":
            return self.sql.from_image(table, image) if self.sql else dict(image)
        return self._build(table, image, self.mode(table))

    def _build(self, table, image, mode):
        row = dict(image)
        if mode == "image":
            return row
        spec = self.cfg["lookup"][table]
        for col, fn in (spec.get("computed") or {}).items():
            row[col] = COMPUTED[fn](row)
        for lk in spec.get("lookups") or []:
            item = self.lookup.get(lk["table"], awmap.render(lk["PK"], row), awmap.render(lk["SK"], row))
            if item is None:
                if self.sql:  # parent copy not there (yet): fall back to the join
                    self.stats["sql"] += 1
                    return self.sql.current(table, image) or self.sql.from_image(table, image)
                raise LookupError("%s: parent %s %s/%s not found" % (table, lk["table"], lk["PK"], lk["SK"]))
            for col, attr in lk["attrs"].items():
                row[col] = item.get(attr)
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

    def refresh(self, ch, now):
        img = ch.after or ch.before
        n = 0
        for r in self.rules:
            if r["changed"] != ch.table:
                continue
            vals = {tcol: img.get(scol) for tcol, scol in r["where"].items()}
            if any(v is None for v in vals.values()):
                continue
            for row in self.rows.by_columns(r["refresh"], vals):
                for t, item in self.items(r["refresh"], row, None, now):
                    n += self.sink.refresh(t, item)
        return n


def tombstone(item, table, position, now, now_epoch):
    return {"PK": item["PK"], "SK": item["SK"], "type": item["type"], "deleted": True, "deleted_at": now,
            "ttl": now_epoch + TOMBSTONE_TTL, "ver": item.get("ver", 1) + 1, "src": "sql", "src_table": table,
            "src_pk": item["src_pk"], "src_lsn": position, "updated_at": now}


# ---------------------------------------------------------------- sinks

class DynamoDBSink:
    def __init__(self, resource):
        self.r = resource

    def get(self, table, pk, sk):
        """Lookup for enrichment (eventually consistent); tombstones count as missing."""
        it = self.r.Table(table).get_item(Key={"PK": pk, "SK": sk}).get("Item")
        return None if it is None or it.get("deleted") else it

    def put(self, table, item, position):
        t = self.r.Table(table)
        try:
            t.put_item(Item=item, ConditionExpression="attribute_not_exists(PK) OR src_lsn < :p", ExpressionAttributeValues={":p": position})
            return True
        except t.meta.client.exceptions.ConditionalCheckFailedException:
            return False

    def refresh(self, table, item):
        """Snapshot copy refresh: update non-key attributes in place; never resurrects tombstones, never moves src_lsn."""
        t = self.r.Table(table)
        attrs = {k: v for k, v in item.items() if k not in META and k != "updated_at"}
        if not attrs:
            return 0
        names = {"#a%d" % i: k for i, k in enumerate(attrs)}
        values = {":v%d" % i: v for i, v in enumerate(attrs.values())}
        values[":u"] = item["updated_at"]
        expr = "SET " + ", ".join("#a%d = :v%d" % (i, i) for i in range(len(attrs))) + ", updated_at = :u"
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

    def get(self, table, pk, sk):
        return self.tables.get(table, {}).get((pk, sk))

    def put(self, table, item, position):
        cur = self.get(table, item["PK"], item["SK"])
        if cur is not None and not cur.get("src_lsn", "") < position:
            return False
        self.tables.setdefault(table, {})[(item["PK"], item["SK"])] = dict(item)
        return True

    def refresh(self, table, item):
        cur = self.get(table, item["PK"], item["SK"])
        if cur is None or cur.get("deleted"):
            return 0
        cur.update({k: v for k, v in item.items() if k not in META})
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
    return v
