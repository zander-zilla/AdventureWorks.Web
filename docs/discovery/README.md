# Phase 1 – Discovery

| File | What |
|---|---|
| [inventory.md](inventory.md) | Generated schema inventory of AdventureWorks2022 + AdventureWorksDW2022 (tables, columns, PK/FK, row counts, indexes, views, procs, functions, triggers) |
| [schema.json](schema.json) | Same, machine-readable (input for the phase-8 mapping file) |
| [domains.md](domains.md) / [domains.json](domains.json) | Proposed domain split, cross-domain break/duplicate decisions, LT→full mapping |
| [domain-diagrams.md](domain-diagrams.md) | Generated mermaid ERD per domain + cross-domain FK list |
| [dw-lineage.md](dw-lineage.md) | DW facts/dims → OLTP sources (input for phase 6) |
| [access-patterns-seed.md](access-patterns-seed.md) | Draft access patterns per domain (input for phase 2) |
| [../design/dynamodb-playbook.md](../design/dynamodb-playbook.md) | Our design method |

Regenerate (before stack running): `scripts/discovery/generate.sh`. CI regenerates and fails if the committed output is stale.
