#!/usr/bin/env python3
"""Generate docs/design/tables/<domain>.md from mapping.yaml + access-pattern-keys.yaml + sample items read from DynamoDB Local.
Run after scripts/loader/load.py."""
import collections, decimal, json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "loader"))
import awmap, ddb, yaml
from boto3.dynamodb.conditions import Key
ROOT = awmap.ROOT
m = awmap.load_mapping()
keys = yaml.safe_load(open(os.path.join(ROOT, "design/mapping/access-pattern-keys.yaml")))["patterns"]
ap = {p["id"]: p for p in json.load(open(os.path.join(ROOT, "docs/design/access-patterns.json")))["patterns"]}
stats = json.load(open(os.path.join(ROOT, "docs/design/load-stats.json")))
r = ddb.resource()

SAMPLES = {  # (PK) partitions shown as sample item collections
 "aw-catalog": ["PRODUCT#000771", "MODEL#0019"], "aw-inventory": ["PRODUCT#000001", "ASSEMBLY#000800"],
 "aw-sales": ["ORDER#0000043659"], "aw-customer": ["BE#000293", "EMAIL#catherine0@adventure-works.com"],
 "aw-purchasing": ["VENDOR#001492"], "aw-hr": ["EMPLOYEE#000004"], "aw-reference": ["COUNTRY#CA"]}
TRADEOFFS = {
 "aw-catalog": [
  "Product page = 2 requests (product collection + model description by culture) instead of copying 6 culture descriptions onto every product (fan-out on description edits).",
  "Name-prefix search and the admin product list share one PRODUCTNAMES partition (504 small items, cacheable) instead of a third GSI; the same items enforce name uniqueness.",
  "Price sort and colour/size filters on category pages are done client-side (<= 43 products per subcategory).",
  "Photos are separate items (binary up to ~26 KB) so the product query stays small; links carry the file name.",
  "stock_qty is a copied attribute owned by Inventory (eventually consistent)."],
 "aw-inventory": [
  "Inventory transactions (current + archive, ~202k) live in the product partition, sorted by date; the hottest product has a few thousand items - fine without LSIs (no 10 GB collection limit).",
  "BOM explosion / where-used are iterative (one Query per assembly per level, max depth 4) rather than a materialized tree.",
  "Work orders by due date are bucketed per month (WODUE#yyyy-mm); a range across months = one Query per month. 'Open' is a filter: all 72,591 historical WOs are closed.",
  "REORDER is a sparse GSI1 partition maintained when stock_qty changes."],
 "aw-sales": [
  "Order history (GSI1) returns headers only; lines come from the order's own partition (SAL-04).",
  "GSI1 is eventually consistent; right after checkout the app reads the order partition with ConsistentRead (D8) and merges it into the list.",
  "Status index is sparse (statuses 1-3 only); shipping an order removes GSI2 keys in the same UpdateItem.",
  "PO-number and approval-code lookups are derived items (2 extra items per order at most) instead of extra GSIs.",
  "Checkout transaction limit (100 actions) caps an order at ~95 lines when cart cleanup is in the same transaction.",
  "Order lines carry immutable product snapshots; addresses/customer/card on the header are as-at-order-time copies."],
 "aw-customer": [
  "Customers live in their person's (or store's) BE# partition, so login = 1 strong GetItem + 1 strong Query; lookup by CustomerID goes through GSI1 (eventual).",
  "Email uniqueness and login use EMAIL#<email> marker items (strongly consistent) rather than a GSI.",
  "The admin customer list is one GSI2 partition (19,820 items, low traffic). Territory lists moved to Redshift (D7).",
  "Full card numbers are NOT migrated (only type, last 4, expiry) - see open question.",
  "Address copies on party links are refreshed by the customer stream via GSI1 ADDRESS#id."],
 "aw-purchasing": [
  "Vendor addresses and contacts are copies of Customer & Party items (vendor BEs), refreshed by the customer stream.",
  "Open POs use derived POSTATUS#<s> items (237 today) instead of a third GSI.",
  "Vendor<->product many-to-many: edge items in the vendor partition + inverted GSI1 on product."],
 "aw-hr": [
  "Org chart uses the hierarchyid path string as GSI2 sort key (single 'ORG' partition of 290 items); subtree = begins_with, chain = one Query per ancestor.",
  "Current department membership is a sparse GSI1 (end_date absent).",
  "Pay and national ID stay in this table only; customer-managed KMS key + separate IAM."],
 "aw-reference": [
  "Small lists are single partitions (COUNTRIES, CURRENCIES, SHIPMETHODS, UNITS, CULTURES) - read once and cached.",
  "FX rates are partitioned per currency pair and sorted by date (latest-on-or-before = Limit 1 descending).",
  "GSI1 resolves StateProvinceID / CurrencyRateID for CDC enrichment."]}

def jsonable(o):
    if isinstance(o, decimal.Decimal): return int(o) if o == int(o) else float(o)
    if isinstance(o, (bytes, bytearray)): return "<binary %d bytes>" % len(o)
    if isinstance(o, dict): return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, list): return [jsonable(v) for v in o]
    return o

def short(item):
    item = jsonable(item)
    for k, v in list(item.items()):
        if isinstance(v, str) and len(v) > 80: item[k] = v[:77] + "..."
    return item

def esc(s): return str(s).replace("|", "\\|")

os.makedirs(os.path.join(ROOT, "docs/design/tables"), exist_ok=True)
for tname, tinfo in m["tables"].items():
    dom = tinfo["domain"]; specs = []
    for src_name, src in m["sources"].items():
        for s in src["items"]:
            if s["table"] == tname: specs.append((src_name, s, src))
    L = ["# %s — `%s`\n" % (dom, tname), "Generated by `scripts/design/table_docs.py` from `design/mapping/mapping.yaml`, `access-pattern-keys.yaml` and sample items read back from DynamoDB Local. "
         "Method: docs/design/dynamodb-playbook.md (The DynamoDB Book ch. 7, 9, 11–14, 16; cited by chapter only).\n",
         "**Table settings:** on-demand, PITR, streams NEW_AND_OLD_IMAGES, TTL attribute `ttl`, GSIs: %s (projection ALL). Items loaded: **%s**.\n" % (", ".join(tinfo["gsis"]) or "none", format(stats["items_per_table"].get(tname, 0), ",")),
         "## Entity chart\n", "| Entity | Source | PK | SK | GSI1PK / GSI1SK | GSI2PK / GSI2SK | Items |", "|---|---|---|---|---|---|---|"]
    for src_name, s, src in specs:
        g1 = "%s / %s" % (s["GSI1PK"], s["GSI1SK"]) if s.get("GSI1PK") else ""
        g2 = "%s / %s" % (s["GSI2PK"], s["GSI2SK"]) if s.get("GSI2PK") else ""
        if s.get("gsi1_when") or s.get("gsi2_when"): g1 += " (sparse)" if s.get("gsi1_when") and g1 else ""; g2 += " (sparse)" if s.get("gsi2_when") and g2 else ""
        flag = " (derived)" if s.get("derived") else (" (copy of %s)" % s["copy_of"] if s.get("copy_of") else "")
        L.append("| %s%s | %s | `%s` | `%s` | %s | %s | %s |" % (s["entity"], flag, src_name, s["PK"], s["SK"], esc(g1) and "`%s`" % esc(g1), esc(g2) and "`%s`" % esc(g2),
                 format(stats["items_per_entity"].get("%s/%s" % (tname, s["entity"]), 0), ",")))
    # item collections diagram
    L += ["\n## Item collections\n", "```mermaid", "flowchart LR"]
    groups = collections.OrderedDict()
    for src_name, s, _ in specs:
        groups.setdefault(re.sub(r"\{[^}]*\}", "x", s["PK"]), []).append(s)
    for i, (pk, ss) in enumerate(groups.items()):
        L.append('  subgraph P%d["PK = %s"]' % (i, pk.replace('"', "'")))
        for j, s in enumerate(ss):
            L.append('    P%d_%d["%s<br/>SK = %s"]' % (i, j, s["entity"], re.sub(r"\{[^}]*\}", "x", s["SK"]).replace('"', "'")))
        L.append("  end")
    for g in tinfo["gsis"]:
        idx = collections.OrderedDict()
        for src_name, s, _ in specs:
            if s.get(g + "PK"): idx.setdefault(re.sub(r"\{[^}]*\}", "x", s[g + "PK"]), []).append(s["entity"])
        for k, (pk, ents) in enumerate(idx.items()):
            L.append('  %s_%d(["%s: %s<br/>%s"])' % (g, k, g, pk.replace('"', "'"), ", ".join(dict.fromkeys(ents))))
    L.append("```\n")
    # snapshots
    snaps = [(sn, x) for sn, s in m["sources"].items() for x in s.get("snapshots", []) if any(i["table"] == tname for i in s["items"])]
    copies = [(sn, s) for sn, src in m["sources"].items() for s in src["items"] if s["table"] == tname and s.get("copy_of")]
    if snaps or copies:
        L += ["## Denormalized / snapshot copies\n", "| Attributes | On items from | Copied from | Owner of refresh | Refresh |", "|---|---|---|---|---|"]
        for sn, x in snaps:
            L.append("| %s | %s | %s | %s | %s |" % (", ".join(x["attrs"]), sn, x["from"], x["owner"], esc(x["refresh"])))
        for sn, s in copies:
            L.append("| whole item (%s) | %s | %s | %s | %s stream |" % (s["entity"], sn, s["copy_of"], s["copy_of"], s["copy_of"]))
        L.append("")
    # access patterns
    L += ["## Access patterns → key conditions\n", "| ID | Question | Operation(s) | Consistency | Notes / compromise |", "|---|---|---|---|---|"]
    for k in keys:
        if k["table"] != tname: continue
        p = ap[k["id"]]
        L.append("| %s | %s | %s | %s | %s |" % (k["id"], esc(p["question"]), "<br>".join("`%s`" % esc(o) for o in k["ops"]), esc(k.get("consistency", p["consistency"])),
                 esc("; ".join(x for x in (k.get("result", ""), k.get("filter", ""), k.get("sort", ""), ("**Compromise:** " + k["compromise"]) if k.get("compromise") else "") if x))))
    L.append("")
    # samples
    L += ["## Sample items (read back from DynamoDB Local)\n"]
    for pk in SAMPLES[tname]:
        items = r.Table(tname).query(KeyConditionExpression=Key("PK").eq(pk), Limit=6)["Items"]
        L += ["Partition `%s` (first %d items):\n" % (pk, len(items)), "```json", json.dumps([short(i) for i in items], indent=1, ensure_ascii=False), "```\n"]
    L += ["## Trade-offs\n"] + ["- " + t for t in TRADEOFFS[tname]] + [""]
    fn = os.path.join(ROOT, "docs/design/tables", dom.lower().replace(" & ", "-").replace(" ", "-") + ".md")
    open(fn, "w").write("\n".join(L) + "\n"); print(fn)
