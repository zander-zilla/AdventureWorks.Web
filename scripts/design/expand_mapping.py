#!/usr/bin/env python3
"""Expand design/mapping/mapping.yaml (authored) into design/mapping/mapping.json (every column listed).
Consumers that cannot read YAML or want explicit column->attribute rows (showcase site, Lambda) read mapping.json."""
import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "loader"))
import awmap, yaml
ROOT = awmap.ROOT
m = awmap.load_mapping()
schema = json.load(open(os.path.join(ROOT, "docs/discovery/schema.json")))["databases"][0]
tables = {t["schema"] + "." + t["table"]: t for t in schema["tables"]}
keys = yaml.safe_load(open(os.path.join(ROOT, "design/mapping/access-pattern-keys.yaml")))["patterns"]
out = {k: m[k] for k in ("version", "conventions", "tables", "table_settings", "excluded", "native_items", "dw_lineage")}
out["generated_from"] = "design/mapping/mapping.yaml"
out["sources"] = {}
for name, src in m["sources"].items():
    t = tables[name]; omit = set(src.get("omit", [])); tr = src.get("transforms", {})
    extra_cols = re.findall(r"\bAS\s+([a-z][a-z0-9_]*)", src.get("source_sql", "") or "")
    cols = [{"column": c["name"], "sql_type": c["type"], "attribute": None if c["name"] in omit else awmap.snake(c["name"]),
             "transform": "omitted" if c["name"] in omit else tr.get(c["name"], "copy")} for c in t["columns"]]
    items = []
    for spec in src["items"]:
        it = {k: v for k, v in spec.items()}
        if spec.get("attributes"):
            it["attribute_list"] = [awmap.snake(a) for a in spec["attributes"]]
        items.append(it)
    out["sources"][name] = {"domain": m["tables"][src["items"][0]["table"]]["domain"], "primary_key": t["primary_key"], "row_count": t["row_count"],
                            "source_sql": src.get("source_sql"), "columns": cols,
                            "derived_attributes": [c for c in dict.fromkeys(extra_cols) if not c.startswith("x_")],
                            "snapshots": src.get("snapshots", []), "omit": src.get("omit", []), "transforms": src.get("transforms", {}), "items": items}
out["access_patterns"] = keys
json.dump(out, open(os.path.join(ROOT, "design/mapping/mapping.json"), "w"), indent=1, default=str)
print(len(out["sources"]), "sources,", sum(len(s["items"]) for s in out["sources"].values()), "item specs,", len(keys), "access patterns")
