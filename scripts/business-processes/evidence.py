"""Render evidence.sql output (metric|key|value) into docs/business-processes/evidence.json."""
import json, sys, collections
out = collections.OrderedDict()
for line in open(sys.argv[1], encoding="utf-8-sig"):
    parts = line.rstrip("\r\n").split("|")
    if len(parts) != 3 or not parts[0] or parts[0].startswith("-"):
        continue
    m, k, v = (p.strip() for p in parts)
    if m == "m":
        continue
    out.setdefault(m, collections.OrderedDict())[k] = int(v) if v.lstrip("-").isdigit() else v
json.dump({"source": "scripts/business-processes/evidence.sql against AdventureWorks2022 (before stack, after reset-demo.sql)",
           "metrics": out}, open(sys.argv[2], "w"), indent=1, sort_keys=False)
open(sys.argv[2], "a").write("\n")
