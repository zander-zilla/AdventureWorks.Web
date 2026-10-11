"""Mapping-driven transform: SQL row -> DynamoDB items. Shared by the bulk loader, the CDC transform and tests.
Everything is driven by design/mapping/mapping.yaml."""
import datetime, decimal, os, re, uuid, xml.etree.ElementTree as ET
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAPPING_PATH = os.path.join(ROOT, "design", "mapping", "mapping.yaml")
# Bulk-load position sorts below every real CDC LSN (10-byte LSN as 20 hex digits).
LOAD_LSN = "0x" + "0" * 20
KEYS = ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK")


def load_mapping(path=MAPPING_PATH):
    with open(path) as f:
        return yaml.safe_load(f)


def snake(name):
    s = re.sub(r"ID(?=[A-Z]|$)", "Id", name)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    return s.lower()


def _iso(v):
    if isinstance(v, datetime.datetime):
        return v.replace(microsecond=0).isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat() + "T00:00:00"
    return str(v)


_FIELD = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def render(template, row):
    def sub(m):
        col, spec = m.group(1), m.group(2)
        v = row[col]
        if v is None:
            raise KeyError("null value for key column %s" % col)
        if not spec:
            return _iso(v) if isinstance(v, (datetime.date, datetime.datetime)) else str(v).strip()
        if spec == "iso":
            return _iso(v)
        if spec == "date":
            return _iso(v)[:10]
        if spec == "ym":
            return _iso(v)[:7]
        if spec == "lower":
            return str(v).strip().lower()
        if spec == "trim":
            return str(v).strip()
        return format(int(v), spec)
    return _FIELD.sub(sub, str(template))


def check(cond, row):
    if not cond:
        return True
    v = row.get(cond["col"])
    op = cond["op"]
    if op == "is_null":
        return v is None
    if op == "not_null":
        return v is not None
    if op == "in":
        return v in cond["value"]
    if op == "lt_col":
        o = row.get(cond["value"])
        return v is not None and o is not None and v < o
    raise ValueError(op)


def xml_map(text):
    if not text:
        return None
    root = ET.fromstring(text)
    out = {}
    for el in root.iter():
        if el is root or len(el):
            continue
        tag = el.tag.split("}")[-1]
        if el.text is not None and el.text.strip():
            out[snake(tag)] = el.text.strip()
    return out


def to_ddb(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return decimal.Decimal(repr(v))
    if isinstance(v, decimal.Decimal):
        return v
    if isinstance(v, (datetime.date, datetime.datetime)):
        return _iso(v)
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return bytes(v) if v else None
    if isinstance(v, str):
        v = v.rstrip() if v.endswith(" ") else v
        return v if v != "" else None
    return str(v)


def src_pk(row, pk_cols):
    return ",".join("%s=%s" % (c, _iso(row[c]) if isinstance(row[c], (datetime.date, datetime.datetime)) else str(row[c]).strip()) for c in pk_cols)


def business_attrs(row, spec, src):
    omit = set(src.get("omit", []))
    transforms = src.get("transforms", {})
    wanted = spec.get("attributes")
    cols = wanted if wanted else [c for c in row if not c.startswith("x_") and c not in omit]
    out = {}
    for c in cols:
        v = row[c]
        if transforms.get(c) == "xml_map":
            v = xml_map(v)
        else:
            v = to_ddb(v)
        if v is not None and v != {}:
            out[snake(c)] = v
    return out


def items_for_row(table_name, src, row, pk_cols, lsn=LOAD_LSN, now=None):
    """Return list of (dynamodb_table, item) for one source row."""
    now = now or datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    result = []
    for spec in src["items"]:
        if not check(spec.get("when"), row):
            continue
        item = business_attrs(row, spec, src)
        item["PK"] = render(spec["PK"], row)
        item["SK"] = render(spec["SK"], row)
        for n in ("1", "2"):
            pk, sk = spec.get("GSI%sPK" % n), spec.get("GSI%sSK" % n)
            if pk and check(spec.get("gsi%s_when" % n), row):
                try:
                    item["GSI%sPK" % n] = render(pk, row)
                    item["GSI%sSK" % n] = render(sk, row)
                except KeyError:
                    pass
        for k, v in (spec.get("extra") or {}).items():
            item[k] = render(v, row) if isinstance(v, str) else v
        if spec.get("ttl_from"):
            t = row[spec["ttl_from"]["col"]]
            item["ttl"] = int((t + datetime.timedelta(days=spec["ttl_from"]["days"])).replace(tzinfo=datetime.timezone.utc).timestamp())
        item.update({"type": spec["entity"], "ver": 1, "src": "sql", "src_table": table_name,
                     "src_pk": src_pk(row, pk_cols), "src_lsn": lsn, "updated_at": now})
        if spec.get("derived"):
            item["derived"] = True
        result.append((spec["table"], item))
    return result


def tombstones_for_row(table_name, src, row, pk_cols, lsn, now=None):
    """D10: SQL delete -> tombstone items with same keys, no GSI attributes, deleted flag."""
    now = now or datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    out = []
    for t, item in items_for_row(table_name, src, row, pk_cols, lsn, now):
        out.append((t, {"PK": item["PK"], "SK": item["SK"], "type": item["type"], "deleted": True, "deleted_at": now,
                        "ver": item["ver"] + 1, "src": "sql", "src_table": table_name, "src_pk": item["src_pk"],
                        "src_lsn": lsn, "updated_at": now}))
    return out
