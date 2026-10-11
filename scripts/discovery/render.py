#!/usr/bin/env python3
"""Render docs/discovery/schema.json and inventory.md from raw per-database JSON produced by inventory.sql."""
import json, sys, os, collections, datetime

src, out = sys.argv[1], sys.argv[2]
dbs = []
for name in ("AdventureWorks2022", "AdventureWorksDW2022"):
    d = json.load(open(os.path.join(src, name + ".json")))
    for t in d.get("tables", []):
        for k in ("columns", "primary_key", "foreign_keys", "indexes", "triggers"):
            t.setdefault(k, [])
        t["primary_key"] = [c["name"] for c in t["primary_key"]]
    for m in d.get("modules", []):
        m["references"] = m.pop("references_", [])
    d.setdefault("modules", []); d.setdefault("triggers", [])
    dbs.append(d)

os.makedirs(out, exist_ok=True)
schema = {"generated_by": "scripts/discovery/generate.sh", "source": "SQL Server 2022, official AdventureWorks 2022 backups",
          "databases": dbs}
json.dump(schema, open(os.path.join(out, "schema.json"), "w"), indent=1, sort_keys=False)

def coltype(c):
    t = c["type"]
    if t in ("nvarchar", "varchar", "nchar", "char", "varbinary", "binary"):
        t += "(%s)" % ("max" if c["max_length"] == -1 else c["max_length"])
    elif t in ("decimal", "numeric"):
        t += "(%s,%s)" % (c["precision"], c["scale"])
    return t

L = []
L.append("# Schema inventory – AdventureWorks2022 (OLTP) and AdventureWorksDW2022\n")
L.append("Generated from the live before-stack databases by `scripts/discovery/generate.sh` "
         "(`inventory.sql` → `render.py`). Machine-readable form: [`schema.json`](schema.json). Do not edit by hand.\n")
L.append("## Headline numbers\n")
L.append("| Database | Schemas | Tables | Columns | Rows | PKs | FKs | Indexes | Views | Procs | Functions | Triggers |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
for d in dbs:
    T = d["tables"]; M = collections.Counter(m["type"] for m in d["modules"])
    fn = sum(v for k, v in M.items() if "FUNCTION" in k)
    L.append("| %s | %d | %d | %d | %s | %d | %d | %d | %d | %d | %d | %d |" % (
        d["database"], len({t["schema"] for t in T}), len(T), sum(len(t["columns"]) for t in T),
        format(sum(t["row_count"] or 0 for t in T), ","), sum(1 for t in T if t["primary_key"]),
        sum(len(t["foreign_keys"]) for t in T), sum(len(t["indexes"]) for t in T),
        M.get("VIEW", 0), M.get("SQL_STORED_PROCEDURE", 0), fn, len(d["triggers"])))
L.append("")
for d in dbs:
    L.append("## %s\n" % d["database"])
    by = collections.defaultdict(list)
    for t in d["tables"]: by[t["schema"]].append(t)
    L.append("### Tables per schema\n")
    L.append("| Schema | Tables | Rows | Tables (rows) |")
    L.append("|---|---|---|---|")
    for s, ts in sorted(by.items()):
        L.append("| %s | %d | %s | %s |" % (s, len(ts), format(sum(t["row_count"] or 0 for t in ts), ","),
                 ", ".join("%s (%s)" % (t["table"], format(t["row_count"] or 0, ",")) for t in ts)))
    L.append("")
    for kind, title in (("VIEW", "Views"), ("SQL_STORED_PROCEDURE", "Stored procedures"), (None, "Functions")):
        ms = [m for m in d["modules"] if (m["type"] == kind if kind else "FUNCTION" in m["type"])]
        if not ms: continue
        L.append("### %s (%d)\n" % (title, len(ms)))
        L.append("| Name | Type | References |"); L.append("|---|---|---|")
        for m in ms:
            refs = ", ".join(sorted({("%s.%s" % (r.get("schema"), r["name"]) if r.get("schema") else r["name"]) for r in m["references"]}))
            L.append("| %s.%s | %s | %s |" % (m["schema"], m["name"], m["type"], refs))
        L.append("")
    if d["triggers"]:
        L.append("### Triggers (%d)\n" % len(d["triggers"]))
        L.append("| Trigger | On |"); L.append("|---|---|")
        for tr in d["triggers"]:
            L.append("| %s | %s |" % (tr["name"], "%s.%s" % (tr["schema"], tr["table"]) if tr.get("table") else tr["scope"]))
        L.append("")
    L.append("### Table details\n")
    for s, ts in sorted(by.items()):
        for t in ts:
            L.append("#### %s.%s — %s rows\n" % (s, t["table"], format(t["row_count"] or 0, ",")))
            L.append("PK: `%s`\n" % ", ".join(t["primary_key"]) if t["primary_key"] else "PK: _none_\n")
            L.append("| Column | Type | Null | Notes |"); L.append("|---|---|---|---|")
            for c in t["columns"]:
                notes = []
                if c.get("identity"): notes.append("identity")
                if c.get("computed"): notes.append("computed `%s`" % c.get("computed_definition", ""))
                if c.get("default"): notes.append("default `%s`" % c["default"])
                L.append("| %s | %s | %s | %s |" % (c["name"], coltype(c), "Y" if c["nullable"] else "", "; ".join(notes).replace("|", "\\|")))
            if t["foreign_keys"]:
                L.append("\nFKs: " + "; ".join("(%s) → %s.%s(%s)" % (", ".join(x["col"] for x in fk["columns"]), fk["ref_schema"], fk["ref_table"],
                         ", ".join(x["ref_col"] for x in fk["columns"])) for fk in t["foreign_keys"]))
            if t["indexes"]:
                L.append("\nIndexes: " + "; ".join("`%s` %s%s (%s)%s" % (i["name"], i["type"].lower(), " unique" if i["unique"] else "",
                         ", ".join(c["col"] for c in i.get("columns", []) if not c["included"]),
                         (" incl. " + ", ".join(c["col"] for c in i.get("columns", []) if c["included"])) if any(c["included"] for c in i.get("columns", [])) else "")
                         for i in t["indexes"]))
            if t["triggers"]:
                L.append("\nTriggers: " + ", ".join(x["name"] for x in t["triggers"]))
            L.append("")
open(os.path.join(out, "inventory.md"), "w").write("\n".join(L) + "\n")
print("\n".join(L[4:9]))
